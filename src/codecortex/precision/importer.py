"""Import a serialized precision index into CodeCortex's typed model."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import unquote, urlparse

from codecortex.precision.models import (
    PrecisionDocument,
    PrecisionIndex,
    PrecisionIndexError,
    PrecisionOccurrence,
    PrecisionRelationship,
    PrecisionSymbol,
    SourceRange,
)
from codecortex.precision.schema import (
    SUPPORTED_PROTOCOL_VERSIONS,
    DocumentField,
    IndexField,
    MetadataField,
    MultiLineRangeField,
    OccurrenceField,
    PositionEncoding,
    RelationshipField,
    SingleLineRangeField,
    SymbolInformationField,
    ToolInfoField,
)
from codecortex.precision.wire import Message, WireFormatError, decode_message


def _range(occurrence: Message) -> SourceRange | None:
    """Decode an occurrence range from either the typed or compact encoding.

    The typed ranges take precedence over the compact repeated-integer encoding
    when both are present, matching the published schema.
    """
    multi = occurrence.message(OccurrenceField.MULTI_LINE_RANGE)
    if multi is not None:
        return SourceRange(
            multi.scalar(MultiLineRangeField.START_LINE),
            multi.scalar(MultiLineRangeField.START_CHARACTER),
            multi.scalar(MultiLineRangeField.END_LINE),
            multi.scalar(MultiLineRangeField.END_CHARACTER),
        )
    single = occurrence.message(OccurrenceField.SINGLE_LINE_RANGE)
    if single is not None:
        line = single.scalar(SingleLineRangeField.LINE)
        return SourceRange(
            line,
            single.scalar(SingleLineRangeField.START_CHARACTER),
            line,
            single.scalar(SingleLineRangeField.END_CHARACTER),
        )
    compact = occurrence.int32s(OccurrenceField.RANGE)
    if len(compact) == 3:
        return SourceRange(compact[0], compact[1], compact[0], compact[2])
    if len(compact) == 4:
        return SourceRange(compact[0], compact[1], compact[2], compact[3])
    if not compact:
        return None
    raise PrecisionIndexError(
        f"occurrence range must hold three or four values; found {len(compact)}"
    )


def _symbol(message: Message) -> PrecisionSymbol:
    return PrecisionSymbol(
        symbol=message.text(SymbolInformationField.SYMBOL),
        display_name=message.text(SymbolInformationField.DISPLAY_NAME),
        kind=message.scalar(SymbolInformationField.KIND),
        documentation=tuple(message.texts(SymbolInformationField.DOCUMENTATION)),
        relationships=tuple(
            PrecisionRelationship(
                symbol=item.text(RelationshipField.SYMBOL),
                is_reference=bool(item.scalar(RelationshipField.IS_REFERENCE)),
                is_implementation=bool(item.scalar(RelationshipField.IS_IMPLEMENTATION)),
                is_type_definition=bool(item.scalar(RelationshipField.IS_TYPE_DEFINITION)),
                is_definition=bool(item.scalar(RelationshipField.IS_DEFINITION)),
            )
            for item in message.messages(SymbolInformationField.RELATIONSHIPS)
            if item.text(RelationshipField.SYMBOL)
        ),
        enclosing_symbol=message.text(SymbolInformationField.ENCLOSING_SYMBOL),
    )


def _document(message: Message) -> PrecisionDocument:
    relative_path = normalize_index_path(message.text(DocumentField.RELATIVE_PATH))
    encoding = _position_encoding(message.scalar(DocumentField.POSITION_ENCODING))
    occurrences: list[PrecisionOccurrence] = []
    for item in message.messages(DocumentField.OCCURRENCES):
        symbol = item.text(OccurrenceField.SYMBOL)
        source_range = _range(item)
        if not symbol or source_range is None:
            continue
        occurrences.append(
            PrecisionOccurrence(
                path=relative_path,
                symbol=symbol,
                range=source_range,
                roles=item.scalar(OccurrenceField.SYMBOL_ROLES),
            )
        )
    text = message.raw(DocumentField.TEXT)
    return PrecisionDocument(
        relative_path=relative_path,
        language=message.text(DocumentField.LANGUAGE),
        occurrences=tuple(occurrences),
        symbols=tuple(
            _symbol(item)
            for item in message.messages(DocumentField.SYMBOLS)
            if item.text(SymbolInformationField.SYMBOL)
        ),
        text_digest=hashlib.blake2b(text, digest_size=16).hexdigest() if text else "",
        position_encoding=encoding,
        text=message.text(DocumentField.TEXT),
    )


def _position_encoding(value: int) -> PositionEncoding:
    """Map the declared encoding, treating an unknown future value as unspecified."""
    try:
        return PositionEncoding(value)
    except ValueError:
        return PositionEncoding.UNSPECIFIED


#: Windows drive-letter prefix, e.g. ``C:\\`` or ``c:/``.
_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")

#: A scheme-qualified path such as ``file://`` or ``https://``.
_URI_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*://")


def normalize_index_path(value: str) -> str:
    """Return an indexed document path as a repository-relative POSIX path.

    The schema requires ``Document.relative_path`` to be repository-relative,
    canonical, ``/``-separated, free of ``.`` and ``..`` components and empty
    components, and to point at a regular file rather than a symlink. Anything
    else is rejected.

    Rejecting rather than sanitising is deliberate. Stripping the leading
    separator off ``/etc/passwd`` yields ``etc/passwd``, which looks like a
    legitimate repository path and would be joined against the project root and
    read. A path that violates the schema is a malformed or hostile index, and
    the honest response is to refuse it, not to invent a plausible path.

    Raises:
        PrecisionIndexError: when the path does not conform to the schema.
    """
    normalized = value.replace("\\", "/").strip()
    if not normalized:
        raise PrecisionIndexError("indexed document is missing its relative path")
    if "\x00" in normalized:
        raise PrecisionIndexError("indexed document path contains a NUL byte")
    if _URI_SCHEME.match(normalized):
        raise PrecisionIndexError(
            f"indexed document path must be repository-relative, not a URI: {normalized!r}"
        )
    if _WINDOWS_DRIVE.match(value.strip()):
        raise PrecisionIndexError(
            f"indexed document path must be repository-relative, not absolute: {normalized!r}"
        )
    if normalized.startswith("/"):
        raise PrecisionIndexError(
            f"indexed document path must not begin with a separator: {normalized!r}"
        )
    segments = normalized.split("/")
    if any(segment == "" for segment in segments):
        raise PrecisionIndexError(
            f"indexed document path has an empty component: {normalized!r}"
        )
    if any(segment in {".", ".."} for segment in segments):
        raise PrecisionIndexError(
            f"indexed document path is not canonical: {normalized!r}"
        )
    return normalized


def decode_project_root(value: str) -> str:
    """Decode ``Metadata.project_root``, which the schema defines as a URI.

    Real indexers emit ``file:///abs/path`` (percent-encoded), and some emit a
    bare filesystem path. Both are decoded to a plain absolute path so the
    value can be *reported*.

    This value is never a trust boundary. CodeCortex resolves indexed documents
    against its own configured project root, so an index claiming a root of
    ``/`` or someone else's home directory cannot redirect a file read. The
    decoded root is kept only for diagnostics and for reporting a mismatch.
    """
    text = value.strip()
    if not text:
        return ""
    parsed = urlparse(text)
    if parsed.scheme != "file":
        # A bare path, a Windows drive letter (parsed as a one-letter scheme),
        # or an unexpected scheme: report it verbatim rather than guessing.
        return text
    path = unquote(parsed.path)
    if parsed.netloc and parsed.netloc not in {"", "localhost"}:
        # file://host/share/... - a UNC path. Preserve it recognisably.
        return f"//{parsed.netloc}{path}"
    # file:///C:/x on Windows decodes to "/C:/x"; drop the leading separator.
    if _WINDOWS_DRIVE.match(path.lstrip("/")):
        return path.lstrip("/")
    return path


def import_index(payload: bytes) -> PrecisionIndex:
    """Decode index bytes, raising :class:`PrecisionIndexError` on malformed input."""
    if not payload:
        raise PrecisionIndexError("precision index is empty")
    try:
        root = decode_message(payload)
    except WireFormatError as exc:
        raise PrecisionIndexError(f"malformed precision index: {exc}") from exc

    try:
        metadata = root.message(IndexField.METADATA)
        protocol_version = metadata.scalar(MetadataField.VERSION) if metadata else 0
        if protocol_version not in SUPPORTED_PROTOCOL_VERSIONS:
            raise PrecisionIndexError(
                f"unsupported precision index schema version: {protocol_version}"
            )
        tool = metadata.message(MetadataField.TOOL_INFO) if metadata else None
        documents = tuple(_document(item) for item in root.messages(IndexField.DOCUMENTS))
        external = tuple(
            _symbol(item)
            for item in root.messages(IndexField.EXTERNAL_SYMBOLS)
            if item.text(SymbolInformationField.SYMBOL)
        )
    except WireFormatError as exc:
        raise PrecisionIndexError(f"malformed precision index: {exc}") from exc

    if not documents:
        raise PrecisionIndexError("precision index contains no documents")
    return PrecisionIndex(
        project_root=decode_project_root(
            metadata.text(MetadataField.PROJECT_ROOT) if metadata else ""
        ),
        tool_name=tool.text(ToolInfoField.NAME) if tool else "",
        tool_version=tool.text(ToolInfoField.VERSION) if tool else "",
        protocol_version=protocol_version,
        documents=documents,
        external_symbols=external,
    )

"""Import a serialized precision index into CodeCortex's typed model."""

from __future__ import annotations

import hashlib

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
    if not relative_path:
        raise PrecisionIndexError("indexed document is missing its relative path")
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
    )


def normalize_index_path(value: str) -> str:
    """Normalize an indexed document path to a repository-relative POSIX path.

    Indexers running on Windows emit backslash separators, and some emit a
    leading ``./``. Both must collapse to the same key the CodeCortex graph uses.
    """
    normalized = value.replace("\\", "/").strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.lstrip("/")


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
        project_root=metadata.text(MetadataField.PROJECT_ROOT) if metadata else "",
        tool_name=tool.text(ToolInfoField.NAME) if tool else "",
        tool_version=tool.text(ToolInfoField.VERSION) if tool else "",
        protocol_version=protocol_version,
        documents=documents,
        external_symbols=external,
    )

"""Precision evidence provider: exact definitions, references, and implementations."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from codecortex.config import CortexConfig
from codecortex.evidence.contracts import EvidenceProvider
from codecortex.evidence.models import (
    EvidenceBundle,
    EvidenceKind,
    EvidenceRecord,
    EvidenceRequest,
    ProviderReport,
    ProviderState,
    TrustTier,
)
from codecortex.precision.identity import SymbolIdentity
from codecortex.precision.index import PrecisionIndexStore, PrecisionStatus
from codecortex.precision.models import PrecisionIndex, PrecisionOccurrence
from codecortex.precision.positions import (
    character_to_protocol,
    encoding_is_undecidable,
    protocol_to_character,
)

PROVIDER_KEY = "precision_index"
PROVENANCE = "precision-index"

#: Confidence assigned to a fresh index entry. Exact evidence is exact; the
#: value exists so ranking has a number, not because resolution is probabilistic.
EXACT_CONFIDENCE = 1.0

#: Confidence retained by a stale index entry. It still points at the right
#: symbol far more often than a name match, but positions may have moved.
STALE_CONFIDENCE = 0.55

#: Confidence for an entry whose columns could not be converted from the
#: indexer's declared encoding into character columns. The symbol is right; the
#: column may be off on a line containing non-ASCII text.
AMBIGUOUS_CONFIDENCE = 0.8

AMBIGUOUS_POSITION_DETAIL = (
    "column could not be converted from the indexer's position encoding, so the "
    "reported column may be inaccurate on lines containing non-ASCII text"
)


@dataclass(frozen=True, slots=True)
class _ResolvedSymbol:
    """A symbol resolved from a caret, with the document that scopes it."""

    symbol: str
    document: str
    ambiguous: bool = False


@dataclass(frozen=True, slots=True)
class PrecisionQuery:
    """A caret position expressed in the one-based convention of the public API."""

    path: str
    line: int
    column: int

    def zero_based(self) -> tuple[int, int]:
        return max(0, self.line - 1), max(0, self.column - 1)


class PrecisionEvidenceProvider(EvidenceProvider):
    """Serve compiler/indexer-grade navigation evidence when an index exists."""

    key = PROVIDER_KEY

    def __init__(self, root: Path, config: CortexConfig | None = None) -> None:
        self.root = root.resolve()
        self.config = config or CortexConfig.load(self.root)
        self.store = PrecisionIndexStore(root=self.root, config=self.config.precision_index)

    # -- capability ---------------------------------------------------------

    def status(self) -> PrecisionStatus:
        return self.store.status()

    async def health(self) -> bool:
        status = await asyncio.to_thread(self.store.status)
        return status.available

    def _report(self, status: PrecisionStatus) -> ProviderReport:
        if not status.configured:
            return ProviderReport(
                provider=self.key,
                state=ProviderState.NOT_CONFIGURED,
                detail=status.detail,
                fallback="structural and heuristic graph resolution",
            )
        if not status.available:
            return ProviderReport(
                provider=self.key,
                state=ProviderState.UNAVAILABLE,
                detail=status.detail,
                fallback="structural and heuristic graph resolution",
            )
        if status.stale:
            return ProviderReport(
                provider=self.key,
                state=ProviderState.STALE,
                detail=status.stale_reason,
                fallback="evidence is marked stale and ranked below fresh structural evidence",
            )
        return ProviderReport(provider=self.key, state=ProviderState.AVAILABLE)

    def _loaded(self) -> tuple[PrecisionIndex | None, PrecisionStatus]:
        status = self.store.status()
        return (self.store.load() if status.available else None), status

    # -- evidence construction ---------------------------------------------

    def _record(
        self,
        occurrence: PrecisionOccurrence,
        kind: EvidenceKind,
        *,
        stale: bool,
        identity: SymbolIdentity,
        index: PrecisionIndex,
        ambiguous: bool = False,
        extra: dict[str, object] | None = None,
    ) -> EvidenceRecord:
        location, position_ambiguous = self._public_location(occurrence, index)
        uncertain = ambiguous or position_ambiguous
        metadata: dict[str, object] = {
            "roles": list(occurrence.role_names()),
            "symbol_identity": identity.to_dict(),
        }
        document = index.document(occurrence.path)
        if document is not None:
            metadata["position_encoding"] = document.position_encoding.name.lower()
            metadata["position_encoding_source"] = document.encoding_source.value
            if document.encoding_detail:
                metadata["position_encoding_detail"] = document.encoding_detail
        if uncertain:
            metadata["position_ambiguous"] = True
            metadata["position_detail"] = AMBIGUOUS_POSITION_DETAIL
        if extra:
            metadata.update(extra)
        # Exactness is a claim about the position, not only about freshness. A
        # position that could not be converted from the indexer's encoding is
        # not exact, so it must not carry the exact tier.
        exact = not stale and not uncertain
        if stale:
            confidence = STALE_CONFIDENCE
        elif uncertain:
            confidence = AMBIGUOUS_CONFIDENCE
        else:
            confidence = EXACT_CONFIDENCE
        return EvidenceRecord(
            kind=kind,
            provider=self.key,
            provenance=PROVENANCE,
            trust=TrustTier.EXACT if exact else TrustTier.INFERRED_HIGH,
            path=occurrence.path,
            start_line=location["start_line"],
            start_column=location["start_column"],
            end_line=location["end_line"],
            end_column=location["end_column"],
            symbol=identity.qualified_name or occurrence.symbol,
            target_symbol=occurrence.symbol,
            content=f"{identity.qualified_name or occurrence.symbol} at {occurrence.path}",
            confidence=confidence,
            exact=exact,
            stale=stale,
            metadata=metadata,
        )

    def _resolve_symbol(
        self, index: PrecisionIndex, query: PrecisionQuery
    ) -> _ResolvedSymbol | None:
        """Resolve a caret to a symbol, converting the caret into index columns.

        The caret arrives as a Python character column. The index stores
        columns in whatever unit the indexer declared, so the caret is
        converted into that unit before it is compared. Skipping this step
        resolves the wrong symbol on any line containing non-ASCII text.
        """
        relative = self.store.relative_path(query.path)
        document = index.document(relative)
        if document is None:
            return None
        line, column = query.zero_based()
        ambiguous = False
        if document.needs_column_conversion:
            line_text = self.store.source_line(document, line)
            if line_text is None:
                # Without the source line the caret cannot be converted. Fall
                # back to the raw column, which is correct for ASCII lines, and
                # mark the result so it is never presented as exact.
                ambiguous = True
            else:
                converted = character_to_protocol(
                    line_text, column, document.position_encoding
                )
                ambiguous = converted.ambiguous or (
                    not document.encoding_authoritative
                    and encoding_is_undecidable(line_text, column)
                )
                column = converted.column
        occurrence = index.occurrence_at(relative, line, column)
        if occurrence is None:
            return None
        return _ResolvedSymbol(
            symbol=occurrence.symbol, document=relative, ambiguous=ambiguous
        )

    def _public_location(
        self, occurrence: PrecisionOccurrence, index: PrecisionIndex
    ) -> tuple[dict[str, int], bool]:
        """Return one-based character coordinates for an occurrence.

        Returns ``(location, ambiguous)``. ``ambiguous`` is set when the
        indexer's columns could not be converted to character columns, which
        means the reported position may be off on a non-ASCII line.
        """
        document = index.document(occurrence.path)
        if document is None or not document.needs_column_conversion:
            return occurrence.range.to_dict(), False
        source = occurrence.range
        start_text = self.store.source_line(document, source.start_line)
        end_text = (
            start_text
            if source.single_line
            else self.store.source_line(document, source.end_line)
        )
        if start_text is None or end_text is None:
            return occurrence.range.to_dict(), True
        encoding = document.position_encoding
        start = protocol_to_character(start_text, source.start_column, encoding)
        end = protocol_to_character(end_text, source.end_column, encoding)
        location = {
            "start_line": source.start_line + 1,
            "start_column": start.column + 1,
            "end_line": source.end_line + 1,
            "end_column": end.column + 1,
        }
        undecidable = not document.encoding_authoritative and (
            encoding_is_undecidable(start_text, start.column)
            or encoding_is_undecidable(end_text, end.column)
        )
        return location, start.ambiguous or end.ambiguous or undecidable

    # -- public queries -----------------------------------------------------

    def symbol_at(self, query: PrecisionQuery) -> dict[str, object]:
        """Return the symbol identity under a caret, with provider state."""
        index, status = self._loaded()
        payload: dict[str, object] = {
            "symbol": None,
            "provider": self._report(status).model_dump(mode="json"),
            "precision": status.to_dict(),
        }
        if index is None:
            return payload
        resolved = self._resolve_symbol(index, query)
        if resolved is None:
            return payload
        information = index.symbol_information(resolved.symbol, resolved.document)
        details: dict[str, object] = (
            information.to_dict()
            if information is not None
            else {"symbol": resolved.symbol}
        )
        details["document"] = resolved.document
        if resolved.ambiguous:
            details["position_ambiguous"] = True
            details["position_detail"] = AMBIGUOUS_POSITION_DETAIL
        payload["symbol"] = details
        return payload

    def _navigate(
        self,
        query: PrecisionQuery,
        kind: EvidenceKind,
    ) -> EvidenceBundle:
        index, status = self._loaded()
        report = self._report(status)
        if index is None:
            return EvidenceBundle(records=[], providers=[report])
        resolved = self._resolve_symbol(index, query)
        if resolved is None:
            return EvidenceBundle(
                records=[],
                providers=[
                    report.model_copy(
                        update={
                            "detail": report.detail
                            or "no indexed symbol covers the requested position",
                        }
                    )
                ],
            )
        return self.evidence_for_symbol(
            resolved.symbol,
            kind,
            index=index,
            status=status,
            document=resolved.document,
            ambiguous=resolved.ambiguous,
        )

    def evidence_for_symbol(
        self,
        symbol: str,
        kind: EvidenceKind,
        *,
        index: PrecisionIndex | None = None,
        status: PrecisionStatus | None = None,
        document: str | None = None,
        ambiguous: bool = False,
    ) -> EvidenceBundle:
        """Return evidence of one kind for an already-resolved symbol identity.

        ``document`` scopes the lookup. It is required for a document-local
        symbol, whose identifier is only unique within the document that
        declares it; without it such a symbol resolves to nothing rather than
        to every same-numbered local in the repository.
        """
        if index is None or status is None:
            index, status = self._loaded()
        report = self._report(status)
        if index is None:
            return EvidenceBundle(records=[], providers=[report])
        stale = status.stale
        identity = SymbolIdentity(raw=symbol)
        information = index.symbol_information(symbol, document)
        if information is not None:
            identity = information.identity
        if kind is EvidenceKind.DEFINITION:
            occurrences = index.definitions_for(symbol, document)
        elif kind is EvidenceKind.IMPLEMENTATION:
            occurrences = index.implementations_for(symbol, document)
        elif kind is EvidenceKind.REFERENCE:
            occurrences = index.references_for(symbol, document)
        else:
            occurrences = index.occurrences_for(symbol, document)
        records = [
            self._record(
                occurrence,
                kind,
                stale=stale,
                identity=identity,
                index=index,
                ambiguous=ambiguous,
            )
            for occurrence in occurrences
        ]
        return EvidenceBundle(records=records, providers=[report])

    def definition(self, query: PrecisionQuery) -> EvidenceBundle:
        return self._navigate(query, EvidenceKind.DEFINITION)

    def references(self, query: PrecisionQuery) -> EvidenceBundle:
        return self._navigate(query, EvidenceKind.REFERENCE)

    def implementations(self, query: PrecisionQuery) -> EvidenceBundle:
        return self._navigate(query, EvidenceKind.IMPLEMENTATION)

    def occurrences(self, symbol: str, document: str | None = None) -> EvidenceBundle:
        index, status = self._loaded()
        if index is None:
            return EvidenceBundle(records=[], providers=[self._report(status)])
        return self.evidence_for_symbol(
            symbol, EvidenceKind.REFERENCE, index=index, status=status, document=document
        )

    def search_symbols(self, term: str, limit: int = 25) -> list[dict[str, object]]:
        """Find indexed symbols whose qualified name contains ``term``."""
        index, _ = self._loaded()
        if index is None:
            return []
        needle = term.strip().lower()
        if not needle:
            return []
        seen: dict[tuple[str, str], dict[str, object]] = {}
        for document in index.documents:
            for symbol in document.symbols:
                identity = symbol.identity
                haystack = (identity.qualified_name or symbol.symbol).lower()
                # Two documents may declare the same local id, so results are
                # keyed by document as well as symbol.
                key = (document.relative_path if identity.is_local else "", symbol.symbol)
                if needle in haystack and key not in seen:
                    seen[key] = {**symbol.to_dict(), "document": document.relative_path}
                    if len(seen) >= limit:
                        return list(seen.values())
        return list(seen.values())

    async def collect(self, request: EvidenceRequest) -> EvidenceBundle:
        """Collect precision evidence for a routed request."""
        if request.path is not None and request.line is not None:
            query = PrecisionQuery(request.path, request.line, request.column or 1)
            kinds = request.kinds or (EvidenceKind.DEFINITION, EvidenceKind.REFERENCE)
            bundles = [
                await asyncio.to_thread(self._navigate, query, kind)
                for kind in kinds
                if kind
                in {
                    EvidenceKind.DEFINITION,
                    EvidenceKind.REFERENCE,
                    EvidenceKind.IMPLEMENTATION,
                }
            ]
            records = [record for bundle in bundles for record in bundle.records]
            providers = bundles[0].providers if bundles else []
            return EvidenceBundle(records=records[: request.limit], providers=providers)
        if request.symbol:
            bundle = await asyncio.to_thread(self.occurrences, request.symbol)
            return EvidenceBundle(
                records=bundle.records[: request.limit], providers=bundle.providers
            )
        status = await asyncio.to_thread(self.store.status)
        return EvidenceBundle(records=[], providers=[self._report(status)])

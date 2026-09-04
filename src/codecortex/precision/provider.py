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

PROVIDER_KEY = "precision_index"
PROVENANCE = "precision-index"

#: Confidence assigned to a fresh index entry. Exact evidence is exact; the
#: value exists so ranking has a number, not because resolution is probabilistic.
EXACT_CONFIDENCE = 1.0

#: Confidence retained by a stale index entry. It still points at the right
#: symbol far more often than a name match, but positions may have moved.
STALE_CONFIDENCE = 0.55


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
        extra: dict[str, object] | None = None,
    ) -> EvidenceRecord:
        location = occurrence.range.to_dict()
        metadata: dict[str, object] = {
            "roles": list(occurrence.role_names()),
            "symbol_identity": identity.to_dict(),
        }
        if extra:
            metadata.update(extra)
        return EvidenceRecord(
            kind=kind,
            provider=self.key,
            provenance=PROVENANCE,
            trust=TrustTier.EXACT if not stale else TrustTier.INFERRED_HIGH,
            path=occurrence.path,
            start_line=location["start_line"],
            start_column=location["start_column"],
            end_line=location["end_line"],
            end_column=location["end_column"],
            symbol=identity.qualified_name or occurrence.symbol,
            target_symbol=occurrence.symbol,
            content=f"{identity.qualified_name or occurrence.symbol} at {occurrence.path}",
            confidence=STALE_CONFIDENCE if stale else EXACT_CONFIDENCE,
            exact=not stale,
            stale=stale,
            metadata=metadata,
        )

    def _resolve_symbol(self, index: PrecisionIndex, query: PrecisionQuery) -> str | None:
        relative = self.store.relative_path(query.path)
        line, column = query.zero_based()
        occurrence = index.occurrence_at(relative, line, column)
        return occurrence.symbol if occurrence else None

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
        symbol = self._resolve_symbol(index, query)
        if symbol is None:
            return payload
        information = index.symbol_information(symbol)
        payload["symbol"] = (
            information.to_dict() if information is not None else {"symbol": symbol}
        )
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
        symbol = self._resolve_symbol(index, query)
        if symbol is None:
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
        return self.evidence_for_symbol(symbol, kind, index=index, status=status)

    def evidence_for_symbol(
        self,
        symbol: str,
        kind: EvidenceKind,
        *,
        index: PrecisionIndex | None = None,
        status: PrecisionStatus | None = None,
    ) -> EvidenceBundle:
        """Return evidence of one kind for an already-resolved symbol identity."""
        if index is None or status is None:
            index, status = self._loaded()
        report = self._report(status)
        if index is None:
            return EvidenceBundle(records=[], providers=[report])
        stale = status.stale
        identity = SymbolIdentity(raw=symbol)
        information = index.symbol_information(symbol)
        if information is not None:
            identity = information.identity
        if kind is EvidenceKind.DEFINITION:
            occurrences = index.definitions_for(symbol)
        elif kind is EvidenceKind.IMPLEMENTATION:
            occurrences = index.implementations_for(symbol)
        elif kind is EvidenceKind.REFERENCE:
            occurrences = index.references_for(symbol)
        else:
            occurrences = index.occurrences_for(symbol)
        records = [
            self._record(occurrence, kind, stale=stale, identity=identity)
            for occurrence in occurrences
        ]
        return EvidenceBundle(records=records, providers=[report])

    def definition(self, query: PrecisionQuery) -> EvidenceBundle:
        return self._navigate(query, EvidenceKind.DEFINITION)

    def references(self, query: PrecisionQuery) -> EvidenceBundle:
        return self._navigate(query, EvidenceKind.REFERENCE)

    def implementations(self, query: PrecisionQuery) -> EvidenceBundle:
        return self._navigate(query, EvidenceKind.IMPLEMENTATION)

    def occurrences(self, symbol: str) -> EvidenceBundle:
        index, status = self._loaded()
        if index is None:
            return EvidenceBundle(records=[], providers=[self._report(status)])
        return self.evidence_for_symbol(
            symbol, EvidenceKind.REFERENCE, index=index, status=status
        )

    def search_symbols(self, term: str, limit: int = 25) -> list[dict[str, object]]:
        """Find indexed symbols whose qualified name contains ``term``."""
        index, _ = self._loaded()
        if index is None:
            return []
        needle = term.strip().lower()
        if not needle:
            return []
        seen: dict[str, dict[str, object]] = {}
        for document in index.documents:
            for symbol in document.symbols:
                identity = symbol.identity
                haystack = (identity.qualified_name or symbol.symbol).lower()
                if needle in haystack and symbol.symbol not in seen:
                    seen[symbol.symbol] = symbol.to_dict()
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

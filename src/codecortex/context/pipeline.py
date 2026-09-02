"""Query-aware context ranking, graph expansion, caching, and budgeting."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path

from codecortex.config import CortexConfig
from codecortex.context.budget import BudgetContextProcessor
from codecortex.core.models import ContextChunk
from codecortex.indexing.graph import ProjectGraph
from codecortex.state import AtomicJsonFile


@dataclass(frozen=True, slots=True)
class ContextMetrics:
    raw_tokens: int
    final_tokens: int
    tokens_saved: int
    reduction: float
    candidates: int
    selected: int
    cache_hit: bool


@dataclass(frozen=True, slots=True)
class ContextResult:
    chunks: tuple[ContextChunk, ...]
    metrics: ContextMetrics


class ContextCache:
    VERSION = 2

    def __init__(self, path: Path, ttl_seconds: int = 600, max_entries: int = 128) -> None:
        self.path = path
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self.state = AtomicJsonFile(path)

    @staticmethod
    def key(query: str, budget: int, fingerprints: list[str], graph_revision: str = "") -> str:
        payload = "\n".join(
            [query.strip().lower(), str(budget), graph_revision, *sorted(fingerprints)]
        )
        return hashlib.blake2b(payload.encode("utf-8"), digest_size=20).hexdigest()

    def _load(self) -> dict[str, dict[str, object]]:
        payload = self.state.read({})
        if not isinstance(payload, dict) or payload.get("version") != self.VERSION:
            return {}
        entries = payload.get("entries", {})
        return dict(entries) if isinstance(entries, dict) else {}

    def get(self, key: str) -> list[ContextChunk] | None:
        entries = self._load()
        item = entries.get(key)
        if not isinstance(item, dict):
            return None
        created = float(item.get("created", 0))
        if time.time() - created > self.ttl_seconds:
            return None
        chunks = item.get("chunks")
        if not isinstance(chunks, list):
            return None
        try:
            return [ContextChunk.model_validate(chunk) for chunk in chunks]
        except (TypeError, ValueError):
            return None

    def put(self, key: str, chunks: list[ContextChunk]) -> None:
        def update(payload: object) -> dict[str, object]:
            current = (
                payload
                if isinstance(payload, dict) and payload.get("version") == self.VERSION
                else {"version": self.VERSION, "entries": {}}
            )
            entries = (
                dict(current.get("entries", {}))
                if isinstance(current.get("entries", {}), dict)
                else {}
            )
            entries[key] = {
                "created": time.time(),
                "chunks": [chunk.model_dump(mode="json") for chunk in chunks],
            }
            ordered = sorted(
                entries.items(),
                key=lambda pair: (
                    float(pair[1].get("created", 0)) if isinstance(pair[1], dict) else 0.0
                ),
                reverse=True,
            )[: self.max_entries]
            return {"version": self.VERSION, "entries": dict(ordered)}

        self.state.update(update, default={})


class ContextPipeline:
    def __init__(
        self, root: Path, graph: ProjectGraph | None = None, cache_ttl_seconds: int = 600
    ) -> None:
        self.root = root.resolve()
        self.graph = graph
        self.budget = BudgetContextProcessor()
        self.cache = ContextCache(
            self.root / ".codecortex" / "cache" / "context.json", ttl_seconds=cache_ttl_seconds
        )

    @staticmethod
    def _terms(text: str) -> set[str]:
        return {
            word.strip(".,:;()[]{}<>\"'`_-+").lower()
            for word in text.split()
            if len(word.strip()) > 2
        }

    @staticmethod
    def _fingerprint(chunk: ContextChunk) -> str:
        normalized = " ".join(chunk.content.lower().split())
        provenance = str(chunk.metadata.get("path") or chunk.source)
        return hashlib.blake2b(f"{provenance}\n{normalized}".encode(), digest_size=12).hexdigest()

    def _graph_revision(self) -> str:
        if self.graph is None:
            return "none"
        lines = [
            *(f"n:{node.id}" for node in sorted(self.graph.nodes, key=lambda item: item.id)),
            *(
                f"e:{edge.source}:{edge.kind}:{edge.target}"
                for edge in sorted(
                    self.graph.edges, key=lambda item: (item.source, item.kind, item.target)
                )
            ),
        ]
        return hashlib.blake2b("\n".join(lines).encode("utf-8"), digest_size=12).hexdigest()

    def _rank(self, query: str, chunks: list[ContextChunk]) -> list[ContextChunk]:
        query_terms = self._terms(query)
        ranked: list[ContextChunk] = []
        for chunk in chunks:
            terms = self._terms(chunk.content)
            overlap = len(query_terms & terms) / max(1, len(query_terms))
            path = str(chunk.metadata.get("path", "")).lower()
            path_boost = 0.12 if any(term in path for term in query_terms) else 0.0
            relevance = min(1.0, chunk.relevance * 0.58 + overlap * 0.42 + path_boost)
            ranked.append(chunk.model_copy(update={"relevance": relevance}))
        return sorted(ranked, key=lambda item: (item.relevance, -item.tokens), reverse=True)

    def _graph_chunks(self, query: str, limit: int = 20) -> list[ContextChunk]:
        if self.graph is None:
            return []
        nodes = self.graph.search(query, limit=8)
        if not nodes:
            return []
        node_ids = {node.id for node in nodes}
        node_map = {node.id: node for node in self.graph.nodes}
        adjacency: dict[str, list[tuple[str, str]]] = {}
        for edge in self.graph.edges:
            adjacency.setdefault(edge.source, []).append((edge.kind, edge.target))
            adjacency.setdefault(edge.target, []).append((f"reverse:{edge.kind}", edge.source))
        lines: list[str] = []
        for node_id in node_ids:
            source = node_map.get(node_id)
            if source is None:
                continue
            for kind, target_id in adjacency.get(node_id, []):
                target = node_map.get(target_id)
                if target is None:
                    continue
                lines.append(f"{source.name} --{kind}--> {target.name}")
                if len(lines) >= limit:
                    break
            if len(lines) >= limit:
                break
        if not lines:
            return []
        content = "\n".join(lines)
        return [
            ContextChunk(
                source="knowledge-graph",
                content=content,
                tokens=self.budget.token_counter.count(content),
                relevance=0.88,
                metadata={"expanded_nodes": [node.name for node in nodes]},
            )
        ]

    @staticmethod
    def _near_deduplicate(chunks: list[ContextChunk]) -> list[ContextChunk]:
        selected: list[ContextChunk] = []
        term_sets: list[tuple[set[str], str]] = []
        for chunk in chunks:
            terms = ContextPipeline._terms(chunk.content)
            provenance = str(chunk.metadata.get("path") or chunk.source)
            duplicate = False
            for existing, existing_provenance in term_sets:
                if provenance != existing_provenance:
                    continue
                union = terms | existing
                similarity = len(terms & existing) / max(1, len(union))
                if similarity >= 0.90:
                    duplicate = True
                    break
            if not duplicate:
                selected.append(chunk)
                term_sets.append((terms, provenance))
        return selected

    async def prepare(self, query: str, chunks: list[ContextChunk], budget: int) -> ContextResult:
        CortexConfig.load(self.root).validate_budget(budget)
        candidates = [*chunks, *self._graph_chunks(query)]
        normalized = [
            chunk.model_copy(update={"tokens": self.budget.token_counter.count(chunk.content)})
            for chunk in candidates
        ]
        raw_tokens = sum(chunk.tokens for chunk in normalized)
        fingerprints = [self._fingerprint(chunk) for chunk in normalized]
        cache_key = self.cache.key(query, budget, fingerprints, self._graph_revision())
        cached = self.cache.get(cache_key)
        if cached is not None:
            final_tokens = sum(chunk.tokens for chunk in cached)
            return ContextResult(
                tuple(cached),
                self._metrics(raw_tokens, final_tokens, len(normalized), len(cached), True),
            )
        ranked = self._rank(query, normalized)
        unique = self._near_deduplicate(ranked)
        fitted = await self.budget.fit(unique, budget)
        self.cache.put(cache_key, fitted)
        final_tokens = sum(chunk.tokens for chunk in fitted)
        return ContextResult(
            tuple(fitted),
            self._metrics(raw_tokens, final_tokens, len(normalized), len(fitted), False),
        )

    @staticmethod
    def _metrics(
        raw_tokens: int, final_tokens: int, candidates: int, selected: int, cache_hit: bool
    ) -> ContextMetrics:
        saved = max(0, raw_tokens - final_tokens)
        return ContextMetrics(
            raw_tokens,
            final_tokens,
            saved,
            saved / raw_tokens if raw_tokens else 0.0,
            candidates,
            selected,
            cache_hit,
        )

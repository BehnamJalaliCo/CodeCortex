"""Query-aware context ranking, graph expansion, caching, and budgeting."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path

from codecortex.context.budget import BudgetContextProcessor
from codecortex.core.models import ContextChunk
from codecortex.indexing.graph import ProjectGraph


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
    VERSION = 1

    def __init__(self, path: Path, ttl_seconds: int = 600, max_entries: int = 128) -> None:
        self.path = path
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries

    @staticmethod
    def key(query: str, budget: int, fingerprints: list[str]) -> str:
        payload = "\n".join([query.strip().lower(), str(budget), *fingerprints])
        return hashlib.blake2b(payload.encode("utf-8"), digest_size=20).hexdigest()

    def _load(self) -> dict[str, dict[str, object]]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if payload.get("version") != self.VERSION:
            return {}
        return dict(payload.get("entries", {}))

    def get(self, key: str) -> list[ContextChunk] | None:
        entries = self._load()
        item = entries.get(key)
        if not item:
            return None
        created = float(item.get("created", 0))
        if time.time() - created > self.ttl_seconds:
            return None
        try:
            return [ContextChunk.model_validate(chunk) for chunk in item["chunks"]]
        except (KeyError, TypeError, ValueError):
            return None

    def put(self, key: str, chunks: list[ContextChunk]) -> None:
        entries = self._load()
        entries[key] = {
            "created": time.time(),
            "chunks": [chunk.model_dump(mode="json") for chunk in chunks],
        }
        ordered = sorted(
            entries.items(),
            key=lambda pair: float(pair[1].get("created", 0)),
            reverse=True,
        )[: self.max_entries]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(
            json.dumps(
                {"version": self.VERSION, "entries": dict(ordered)},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        temp.replace(self.path)


class ContextPipeline:
    def __init__(
        self,
        root: Path,
        graph: ProjectGraph | None = None,
        cache_ttl_seconds: int = 600,
    ) -> None:
        self.root = root.resolve()
        self.graph = graph
        self.budget = BudgetContextProcessor()
        self.cache = ContextCache(
            self.root / ".codecortex" / "cache" / "context.json",
            ttl_seconds=cache_ttl_seconds,
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
        return hashlib.blake2b(normalized.encode("utf-8"), digest_size=12).hexdigest()

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
        lines: list[str] = []
        for edge in self.graph.edges:
            if edge.source in node_ids or edge.target in node_ids:
                source = next((node for node in self.graph.nodes if node.id == edge.source), None)
                target = next((node for node in self.graph.nodes if node.id == edge.target), None)
                if source and target:
                    lines.append(f"{source.name} --{edge.kind}--> {target.name}")
                if len(lines) >= limit:
                    break
        if not lines:
            return []
        content = "\n".join(lines)
        return [
            ContextChunk(
                source="knowledge-graph",
                content=content,
                tokens=max(1, len(content) // 4),
                relevance=0.88,
                metadata={"expanded_nodes": [node.name for node in nodes]},
            )
        ]

    @staticmethod
    def _near_deduplicate(chunks: list[ContextChunk]) -> list[ContextChunk]:
        selected: list[ContextChunk] = []
        term_sets: list[set[str]] = []
        for chunk in chunks:
            terms = ContextPipeline._terms(chunk.content)
            duplicate = False
            for existing in term_sets:
                union = terms | existing
                similarity = len(terms & existing) / max(1, len(union))
                if similarity >= 0.90:
                    duplicate = True
                    break
            if not duplicate:
                selected.append(chunk)
                term_sets.append(terms)
        return selected

    async def prepare(
        self,
        query: str,
        chunks: list[ContextChunk],
        budget: int,
    ) -> ContextResult:
        candidates = [*chunks, *self._graph_chunks(query)]
        raw_tokens = sum(chunk.tokens for chunk in candidates)
        fingerprints = [self._fingerprint(chunk) for chunk in candidates]
        cache_key = self.cache.key(query, budget, fingerprints)
        cached = self.cache.get(cache_key)
        if cached is not None:
            final_tokens = sum(chunk.tokens for chunk in cached)
            return ContextResult(
                tuple(cached),
                self._metrics(raw_tokens, final_tokens, len(candidates), len(cached), True),
            )
        ranked = self._rank(query, candidates)
        unique = self._near_deduplicate(ranked)
        fitted = await self.budget.fit(unique, budget)
        self.cache.put(cache_key, fitted)
        final_tokens = sum(chunk.tokens for chunk in fitted)
        return ContextResult(
            tuple(fitted),
            self._metrics(raw_tokens, final_tokens, len(candidates), len(fitted), False),
        )

    @staticmethod
    def _metrics(
        raw_tokens: int,
        final_tokens: int,
        candidates: int,
        selected: int,
        cache_hit: bool,
    ) -> ContextMetrics:
        saved = max(0, raw_tokens - final_tokens)
        reduction = saved / raw_tokens if raw_tokens else 0.0
        return ContextMetrics(
            raw_tokens=raw_tokens,
            final_tokens=final_tokens,
            tokens_saved=saved,
            reduction=reduction,
            candidates=candidates,
            selected=selected,
            cache_hit=cache_hit,
        )

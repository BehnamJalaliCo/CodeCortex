"""One-command project setup and integration discovery."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from codecortex.indexing.incremental import IncrementalIndex, IndexStats
from codecortex.indexing.indexer import ProjectIndexer
from codecortex.memory.knowledge import ProjectKnowledge, ProjectKnowledgeExtractor


@dataclass(frozen=True, slots=True)
class SetupResult:
    index: IndexStats
    graph_nodes: int
    graph_edges: int
    symbols: int
    languages: tuple[str, ...]
    knowledge: ProjectKnowledge
    detected_agents: tuple[str, ...]
    integration_file: Path


class ProjectSetup:
    AGENTS = {
        "Claude Code": ("claude",),
        "Codex": ("codex",),
        "OpenCode": ("opencode",),
        "Gemini CLI": ("gemini",),
    }

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.state = self.root / ".codecortex"

    def detect_agents(self) -> tuple[str, ...]:
        detected = [
            name
            for name, commands in self.AGENTS.items()
            if any(shutil.which(command) for command in commands)
        ]
        if (self.root / ".cursor").exists():
            detected.append("Cursor")
        return tuple(sorted(set(detected)))

    def _write_config(self) -> None:
        config = {
            "version": 1,
            "context_budget": 32000,
            "hard_context_limit": 128000,
            "telemetry": True,
        }
        path = self.state / "config.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(config, indent=2), encoding="utf-8")

    def _write_integration(self, detected: tuple[str, ...]) -> Path:
        path = self.state / "integrations" / "mcp.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "mcpServers": {
                "codecortex": {
                    "command": "cortex",
                    "args": ["mcp", "--path", str(self.root)],
                }
            },
            "detectedAgents": list(detected),
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def run(self) -> SetupResult:
        self._write_config()
        index = IncrementalIndex(self.root).refresh()
        graph = ProjectIndexer(self.root).build()
        graph_path = self.state / "index" / "graph.json"
        graph.save(graph_path)
        knowledge = ProjectKnowledgeExtractor(self.root).extract()
        ProjectKnowledgeExtractor(self.root).save(knowledge)
        detected = self.detect_agents()
        integration = self._write_integration(detected)
        counts = graph.counts()
        symbol_count = sum(
            count for kind, count in counts.items() if kind not in {"file", "module", "reference"}
        )
        return SetupResult(
            index=index,
            graph_nodes=len(graph.nodes),
            graph_edges=len(graph.edges),
            symbols=symbol_count,
            languages=tuple(name for name, _ in knowledge.languages),
            knowledge=knowledge,
            detected_agents=detected,
            integration_file=integration,
        )

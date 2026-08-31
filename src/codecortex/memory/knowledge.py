"""Automatic project knowledge extraction and persistence."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

from codecortex.git_intelligence import GitIntelligence
from codecortex.memory.json_store import JsonMemoryStore

_LANGUAGE_BY_SUFFIX = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".c": "C",
    ".h": "C/C++",
    ".cc": "C++",
    ".cpp": "C++",
    ".cxx": "C++",
    ".hpp": "C++",
    ".cs": "C#",
    ".php": "PHP",
    ".rb": "Ruby",
}

_PACKAGE_FILES = {
    "pyproject.toml": "Python/pip",
    "requirements.txt": "Python/pip",
    "package.json": "Node.js",
    "pnpm-lock.yaml": "pnpm",
    "yarn.lock": "Yarn",
    "go.mod": "Go modules",
    "Cargo.toml": "Cargo",
    "pom.xml": "Maven",
    "build.gradle": "Gradle",
    "composer.json": "Composer",
    "Gemfile": "Bundler",
}

_TEST_MARKERS = {
    "pytest": ("pytest.ini", "conftest.py", "pytest"),
    "vitest": ("vitest.config", "vitest"),
    "jest": ("jest.config", "jest"),
    "go test": ("_test.go",),
    "cargo test": ("#[test]",),
    "JUnit": ("junit", "@test"),
    "RSpec": ("spec_helper", "rspec"),
}

_ARCHITECTURE_DIRS = {
    "controllers": "controller layer",
    "controller": "controller layer",
    "services": "service layer",
    "service": "service layer",
    "repositories": "repository layer",
    "repository": "repository layer",
    "models": "model layer",
    "domain": "domain layer",
    "api": "API layer",
    "routes": "routing layer",
    "adapters": "adapter layer",
    "ports": "ports layer",
    "core": "core layer",
    "infra": "infrastructure layer",
    "infrastructure": "infrastructure layer",
}

_ENTRY_NAMES = {
    "main.py",
    "app.py",
    "manage.py",
    "index.js",
    "index.ts",
    "server.js",
    "server.ts",
    "main.go",
    "main.rs",
    "Program.cs",
    "Main.java",
}

_EXCLUDED = {".git", ".codecortex", ".venv", "venv", "node_modules", "dist", "build"}


@dataclass(frozen=True, slots=True)
class ProjectKnowledge:
    languages: tuple[tuple[str, int], ...]
    package_systems: tuple[str, ...]
    entry_points: tuple[str, ...]
    test_frameworks: tuple[str, ...]
    architecture: tuple[str, ...]
    hot_files: tuple[str, ...]

    def facts(self) -> dict[str, str]:
        return {
            "languages": ", ".join(f"{name} ({count})" for name, count in self.languages),
            "package_systems": ", ".join(self.package_systems) or "unknown",
            "entry_points": ", ".join(self.entry_points) or "not detected",
            "test_frameworks": ", ".join(self.test_frameworks) or "not detected",
            "architecture": ", ".join(self.architecture) or "no strong convention detected",
            "hot_files": ", ".join(self.hot_files) or "not available",
        }


class ProjectKnowledgeExtractor:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _files(self) -> list[Path]:
        result: list[Path] = []
        for path in self.root.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(self.root)
            if any(part in _EXCLUDED for part in relative.parts):
                continue
            result.append(path)
        return result

    def extract(self) -> ProjectKnowledge:
        files = self._files()
        languages: Counter[str] = Counter()
        package_systems: set[str] = set()
        entry_points: list[str] = []
        architecture: set[str] = set()
        searchable: list[str] = []

        for path in files:
            relative = path.relative_to(self.root)
            language = _LANGUAGE_BY_SUFFIX.get(path.suffix.lower())
            if language:
                languages[language] += 1
            package = _PACKAGE_FILES.get(path.name)
            if package:
                package_systems.add(package)
            if path.name in _ENTRY_NAMES:
                entry_points.append(relative.as_posix())
            for part in relative.parts[:-1]:
                marker = _ARCHITECTURE_DIRS.get(part.lower())
                if marker:
                    architecture.add(marker)
            if path.stat().st_size <= 512_000:
                try:
                    searchable.append(path.read_text(encoding="utf-8").lower())
                except (OSError, UnicodeDecodeError):
                    pass

        joined = "\n".join(searchable)
        test_frameworks = {
            name
            for name, markers in _TEST_MARKERS.items()
            if any(marker.lower() in joined or any(marker.lower() in p.name.lower() for p in files)
                   for marker in markers)
        }
        git = GitIntelligence(self.root).analyze(limit=300)
        return ProjectKnowledge(
            languages=tuple(languages.most_common()),
            package_systems=tuple(sorted(package_systems)),
            entry_points=tuple(sorted(set(entry_points))),
            test_frameworks=tuple(sorted(test_frameworks)),
            architecture=tuple(sorted(architecture)),
            hot_files=tuple(item.path for item in git.hot_files[:10]),
        )

    def save(self, knowledge: ProjectKnowledge | None = None) -> Path:
        knowledge = knowledge or self.extract()
        path = self.root / ".codecortex" / "knowledge" / "project.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        temp.write_text(
            json.dumps(asdict(knowledge), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp.replace(path)
        return path

    async def remember(
        self,
        store: JsonMemoryStore,
        namespace: str = "project_knowledge",
    ) -> ProjectKnowledge:
        knowledge = self.extract()
        self.save(knowledge)
        for key, value in knowledge.facts().items():
            await store.put(namespace, key, value)
        return knowledge

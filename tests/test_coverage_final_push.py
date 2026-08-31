from __future__ import annotations

import ast
import builtins
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

import codecortex.backends.factory as backend_factory
import codecortex.evaluation.external as external
from codecortex.evaluation.external import (
    DeterministicGrader,
    EvaluationCase,
    EvaluationExpectation,
    EvaluationOutput,
    EvaluationReport,
    EvaluationResult,
    ExternalEvaluationSuite,
    Grade,
    SubprocessEvaluationTarget,
)
from codecortex.indexing.relationships import Relationship, RelationshipExtractor
from codecortex.languages.registry import LanguageRegistry, ParsedUnit
from codecortex.retrieval.index import SemanticDocument, SemanticIndex
from codecortex.retrieval.providers import (
    FeatureHashEmbeddingProvider,
    SentenceTransformerEmbeddingProvider,
)


def test_relationship_extractor_python_paths_and_helpers() -> None:
    extractor = RelationshipExtractor()
    source = """
import os
from pkg.mod import thing

class Child(Base):
    def method(self):
        helper()
        self.other()

async def worker():
    await service.run()
"""
    relationships = extractor.extract(Path("sample.py"), source)
    assert Relationship("imports", "os", 2) in relationships
    assert Relationship("imports", "pkg.mod", 3) in relationships
    assert any(item.kind == "inherits" and item.target == "Base" for item in relationships)
    assert any(
        item.kind == "calls" and item.target == "helper" and item.source_symbol == "method"
        for item in relationships
    )
    assert any(
        item.kind == "calls" and item.target == "run" and item.source_symbol == "worker"
        for item in relationships
    )
    assert extractor.extract(Path("broken.py"), "def broken(:") == []

    assert extractor._python_name(ast.Name(id="value")) == "value"
    attribute = ast.Attribute(value=ast.Name(id="obj"), attr="field")
    assert extractor._python_name(attribute) == "obj.field"
    orphan_attribute = ast.Attribute(value=ast.Constant(value=1), attr="field")
    assert extractor._python_name(orphan_attribute) == "field"
    assert extractor._python_name(ast.Constant(value=1)) is None


@pytest.mark.parametrize(
    ("suffix", "source", "target"),
    [
        (".js", 'import value from "pkg-js";\nvalue();', "pkg-js"),
        (".tsx", 'import "pkg-ts";\nrender();', "pkg-ts"),
        (".go", 'import "fmt"\nPrintln()', "fmt"),
        (".rs", "use std::fmt;\nrender();", "std::fmt"),
        (".java", "import java.util.List;\nrender();", "java.util.List"),
        (".cs", "import System.Text;\nrender();", "System.Text"),
        (".c", "#include <stdio.h>\nrender();", "stdio.h"),
        (".cpp", '#include "thing.hpp"\nrender();', "thing.hpp"),
        (".php", "use Vendor\\Package;\nrender();", "Vendor\\Package"),
        (".rb", 'require_relative "helper"\nrender()', "helper"),
    ],
)
def test_relationship_extractor_import_languages(
    suffix: str, source: str, target: str
) -> None:
    relationships = RelationshipExtractor().extract(Path(f"sample{suffix}"), source)
    assert any(item.kind == "imports" and item.target == target for item in relationships)


def test_relationship_extractor_inheritance_calls_unknown_and_dedupe() -> None:
    extractor = RelationshipExtractor()
    source = """
class Child extends Base implements First, Second {
  if (ready) {}
  realCall();
  realCall();
}
"""
    relationships = extractor.extract(Path("sample.js"), source)
    assert any(item.kind == "inherits" and item.target == "Base" for item in relationships)
    assert {item.target for item in relationships if item.kind == "implements"} == {
        "First",
        "Second",
    }
    assert any(item.kind == "calls" and item.target == "realCall" for item in relationships)
    assert not any(item.kind == "calls" and item.target == "if" for item in relationships)
    assert extractor._imports(Path("sample.txt"), "call()") == []

    item = Relationship("calls", "same", 1)
    assert extractor._dedupe([item, item]) == [item]


def test_deterministic_grader_pass_and_fail_paths() -> None:
    case = EvaluationCase(
        id="case",
        prompt="prompt",
        expectation=EvaluationExpectation(
            required_strings=("hello", "missing"),
            forbidden_strings=("secret",),
            required_paths=("src/a.py", "src/missing.py"),
            max_tokens=10,
            max_tool_calls=2,
        ),
    )
    output = EvaluationOutput(
        answer="HELLO secret",
        files_touched=("src\\a.py",),
        tokens=11,
        tool_calls=3,
    )
    grade = DeterministicGrader().grade(case, output)
    assert not grade.passed
    assert grade.score == pytest.approx(2 / 7)
    assert "required-string:missing" in grade.failures
    assert "forbidden-string:secret" in grade.failures
    assert "required-path:src/missing.py" in grade.failures
    assert "max-tokens:10" in grade.failures
    assert "max-tool-calls:2" in grade.failures

    empty = DeterministicGrader().grade(
        EvaluationCase(id="empty", prompt="p"), EvaluationOutput(answer="anything")
    )
    assert empty.passed and empty.score == 1.0 and empty.checks == ()


def test_evaluation_report_summary_save_and_suite_load(tmp_path: Path) -> None:
    result = EvaluationResult(
        case_id="one",
        target="fake",
        duration_ms=20.0,
        output=EvaluationOutput(answer="ok", tokens=10, tool_calls=2),
        grade=Grade(True, 1.0, ("ok",), ()),
    )
    report = EvaluationReport(
        run_id="run",
        suite_name="suite",
        suite_version=1,
        target="fake",
        created_at="now",
        results=(result,),
    )
    assert report.summary() == {
        "cases": 1.0,
        "success_rate": 1.0,
        "avg_score": 1.0,
        "execution_success_rate": 1.0,
        "avg_duration_ms": 20.0,
        "avg_tokens": 10.0,
        "avg_tool_calls": 2.0,
    }
    empty = EvaluationReport("r", "s", 1, "t", "now", ())
    assert empty.summary()["cases"] == 0.0
    assert empty.summary()["success_rate"] == 0.0

    report_path = tmp_path / "nested" / "report.json"
    report.save(report_path)
    saved = json.loads(report_path.read_text(encoding="utf-8"))
    assert saved["summary"]["avg_score"] == 1.0

    suite_path = tmp_path / "suite.json"
    suite_path.write_text(
        json.dumps(
            {
                "version": 1,
                "name": "loaded",
                "cases": [
                    {
                        "id": "c1",
                        "prompt": "Do it",
                        "expectation": {
                            "required_strings": ["done"],
                            "forbidden_strings": ["bad"],
                            "required_paths": ["src/a.py"],
                            "max_tokens": 50,
                            "max_tool_calls": 5,
                        },
                        "metadata": {"difficulty": 2},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    suite = ExternalEvaluationSuite.load(suite_path)
    assert suite.name == "loaded"
    assert suite.cases[0].metadata == {"difficulty": "2"}
    assert suite.cases[0].expectation.max_tokens == 50

    suite_path.write_text('{"version": 999}', encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported evaluation suite version"):
        ExternalEvaluationSuite.load(suite_path)


class _Process:
    def __init__(
        self,
        stdout: bytes = b'{"answer":"ok","files_touched":["a.py"],"tokens":4,"tool_calls":1,"metadata":{"x":1}}',
        stderr: bytes = b"",
        returncode: int = 0,
        timeout: bool = False,
    ) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.timeout = timeout
        self.killed = False
        self.waited = False
        self.request: bytes | None = None

    async def communicate(self, request: bytes) -> tuple[bytes, bytes]:
        self.request = request
        if self.timeout:
            raise TimeoutError
        return self.stdout, self.stderr

    def kill(self) -> None:
        self.killed = True

    async def wait(self) -> None:
        self.waited = True


@pytest.mark.asyncio
async def test_subprocess_evaluation_target_success_and_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(ValueError, match="argv cannot be empty"):
        SubprocessEvaluationTarget("bad", ())

    process = _Process()

    async def _create(*args: Any, **kwargs: Any) -> _Process:
        assert args == ("agent", "--json")
        assert kwargs["cwd"] == str(tmp_path)
        assert kwargs["env"]["EXTRA"] == "1"
        return process

    monkeypatch.setattr(external.asyncio, "create_subprocess_exec", _create)
    target = SubprocessEvaluationTarget(
        "agent",
        ("agent", "--json"),
        cwd=tmp_path,
        env={"EXTRA": "1"},
        timeout_seconds=2,
    )
    output = await target.run(EvaluationCase(id="x", prompt="hello"))
    assert output.answer == "ok"
    assert output.files_touched == ("a.py",)
    assert output.tokens == 4 and output.tool_calls == 1
    assert output.metadata == {"x": 1}
    assert process.request and b'"prompt": "hello"' in process.request

    timeout_process = _Process(timeout=True)

    async def _create_timeout(*args: Any, **kwargs: Any) -> _Process:
        return timeout_process

    monkeypatch.setattr(external.asyncio, "create_subprocess_exec", _create_timeout)
    with pytest.raises(RuntimeError, match="timed out"):
        await target.run(EvaluationCase(id="timeout", prompt="p"))
    assert timeout_process.killed and timeout_process.waited

    failed_process = _Process(stderr=b"very bad", returncode=7)

    async def _create_failed(*args: Any, **kwargs: Any) -> _Process:
        return failed_process

    monkeypatch.setattr(external.asyncio, "create_subprocess_exec", _create_failed)
    with pytest.raises(RuntimeError, match="exited 7: very bad"):
        await target.run(EvaluationCase(id="failed", prompt="p"))

    invalid_process = _Process(stdout=b"not-json")

    async def _create_invalid(*args: Any, **kwargs: Any) -> _Process:
        return invalid_process

    monkeypatch.setattr(external.asyncio, "create_subprocess_exec", _create_invalid)
    with pytest.raises(RuntimeError, match="invalid JSON"):
        await target.run(EvaluationCase(id="invalid", prompt="p"))


@pytest.mark.asyncio
async def test_external_suite_run_success_and_execution_error() -> None:
    cases = [
        EvaluationCase(
            id="ok",
            prompt="ok",
            expectation=EvaluationExpectation(required_strings=("done",)),
        ),
        EvaluationCase(id="boom", prompt="boom"),
    ]

    class _Target:
        name = "target"

        async def run(self, case: EvaluationCase) -> EvaluationOutput:
            if case.id == "boom":
                raise RuntimeError("failure")
            return EvaluationOutput(answer="done", tokens=3, tool_calls=1)

    report = await ExternalEvaluationSuite("suite", cases).run(_Target())
    assert report.suite_name == "suite" and report.target == "target"
    assert report.results[0].grade.passed
    assert report.results[1].error == "RuntimeError: failure"
    assert report.results[1].grade.failures == ("execution-error",)
    assert len(report.run_id) == 32


class _EmbeddingProvider:
    name = "fake"
    dimensions = 2

    def embed(self, texts: list[str]) -> list[list[float]]:
        mapping = {
            "left": [1.0, 0.0],
            "right": [0.0, 1.0],
            "query": [1.0, 0.0],
            "zero": [0.0, 0.0],
        }
        return [mapping.get(text, [0.5, 0.5]) for text in texts]


def test_semantic_index_lifecycle_search_and_persistence(tmp_path: Path) -> None:
    provider = _EmbeddingProvider()
    path = tmp_path / "semantic.json"
    index = SemanticIndex(provider, path)
    assert index.document_ids == set()
    assert index.search("query") == []
    index.upsert([])

    left = SemanticDocument("left", "left", {"kind": "a"})
    right = SemanticDocument("right", "right")
    index.upsert([left, right])
    assert index.document_ids == {"left", "right"}
    matches = index.search("query", limit=1)
    assert matches[0].document.id == "left" and matches[0].score == pytest.approx(1.0)
    assert index.search("query", min_score=1.1) == []

    loaded = SemanticIndex(provider, path)
    assert loaded.document_ids == {"left", "right"}
    assert loaded.search("query")[0].document.metadata == {"kind": "a"}

    loaded.delete({"left", "missing"})
    assert loaded.document_ids == {"right"}
    loaded.replace([left])
    assert loaded.document_ids == {"left"}
    loaded.replace([])
    assert loaded.document_ids == set()

    no_path = SemanticIndex(provider)
    no_path.save()
    no_path.load()
    assert SemanticIndex._cosine([1.0], [1.0, 2.0]) == -1.0
    assert SemanticIndex._cosine([0.0, 0.0], [0.0, 0.0]) == 0.0


def test_semantic_index_rejects_bad_persisted_payloads(tmp_path: Path) -> None:
    provider = _EmbeddingProvider()
    path = tmp_path / "semantic.json"

    path.write_text("not-json", encoding="utf-8")
    assert SemanticIndex(provider, path).document_ids == set()

    base = {
        "version": 1,
        "provider": "fake",
        "dimensions": 2,
        "documents": {"x": {"id": "x", "text": "left"}},
        "vectors": {"x": [1, 0], "orphan": [0, 1]},
    }
    for key, value in [
        ("version", 2),
        ("provider", "other"),
        ("dimensions", 99),
    ]:
        payload = dict(base)
        payload[key] = value
        path.write_text(json.dumps(payload), encoding="utf-8")
        assert SemanticIndex(provider, path).document_ids == set()

    path.write_text(json.dumps(base), encoding="utf-8")
    loaded = SemanticIndex(provider, path)
    assert loaded.document_ids == {"x"}
    assert set(loaded._vectors) == {"x"}


def test_embedding_providers_fallback_and_optional_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="dimensions must be >= 64"):
        FeatureHashEmbeddingProvider(32)
    provider = FeatureHashEmbeddingProvider(64)
    first, empty = provider.embed(["Alpha beta alpha", ""])
    assert len(first) == 64 and len(empty) == 64
    assert sum(value * value for value in first) == pytest.approx(1.0)
    assert sum(empty) == 0.0
    assert provider.embed(["same"])[0] == provider.embed(["same"])[0]

    real_import = builtins.__import__

    def _missing_import(
        name: str,
        globals: dict[str, Any] | None = None,
        locals: dict[str, Any] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> Any:
        if name == "sentence_transformers":
            raise ImportError("missing")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _missing_import)
    with pytest.raises(RuntimeError, match="semantic.*extra"):
        SentenceTransformerEmbeddingProvider()
    monkeypatch.setattr(builtins, "__import__", real_import)

    module = ModuleType("sentence_transformers")

    class _Model:
        def __init__(self, name: str) -> None:
            self.name = name

        def encode(self, texts: list[str], normalize_embeddings: bool) -> list[list[int]]:
            assert normalize_embeddings is True
            return [[1, 2, 3] for _ in texts]

    module.SentenceTransformer = _Model  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sentence_transformers", module)
    neural = SentenceTransformerEmbeddingProvider("model")
    assert neural.name == "sentence-transformer:model" and neural.dimensions == 3
    assert neural.embed(["a", "b"]) == [[1.0, 2.0, 3.0], [1.0, 2.0, 3.0]]


def test_backend_factory_modes_and_activation(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Registry:
        def __init__(self) -> None:
            self.registered: list[Any] = []

        def register(self, adapter: Any) -> None:
            self.registered.append(adapter)

    class _Manager:
        def __init__(self) -> None:
            self.installed = {"graph", "context"}

        def is_installed(self, spec: Any) -> bool:
            return spec.key in self.installed

    registry = _Registry()
    manager = _Manager()
    config = SimpleNamespace(project_root=Path("/tmp/project"))
    specs = {
        key: SimpleNamespace(key=key, configured=True)
        for key in ("graph", "symbols", "context")
    }

    monkeypatch.setattr(backend_factory, "build_default_registry", lambda *a, **k: registry)
    monkeypatch.setattr(backend_factory, "BackendManager", lambda: manager)
    monkeypatch.setattr(backend_factory, "BACKENDS", specs)
    monkeypatch.setattr(
        backend_factory,
        "GraphBackendAdapter",
        lambda root, backend_manager: SimpleNamespace(key="graph"),
    )
    monkeypatch.setattr(
        backend_factory,
        "SymbolBackendAdapter",
        lambda root, backend_manager: SimpleNamespace(key="symbols"),
    )
    monkeypatch.setattr(
        backend_factory,
        "ContextBackendAdapter",
        lambda root, backend_manager: SimpleNamespace(key="context"),
    )
    monkeypatch.setattr(
        backend_factory,
        "IntegratedContextProcessor",
        lambda backend: ("processor", getattr(backend, "key", None)),
    )

    monkeypatch.setenv("CODECORTEX_BACKENDS", "builtin")
    stack = backend_factory.build_backend_stack(config, object())  # type: ignore[arg-type]
    assert stack.active == () and stack.context_processor == ("processor", None)

    monkeypatch.setenv("CODECORTEX_BACKENDS", "invalid")
    assert backend_factory.build_backend_stack(config, object()).active == ()  # type: ignore[arg-type]

    registry.registered.clear()
    monkeypatch.setenv("CODECORTEX_BACKENDS", "mature")
    external_stack = backend_factory.build_backend_stack(config, object())  # type: ignore[arg-type]
    assert external_stack.active == ("graph", "symbols", "context")
    assert [item.key for item in registry.registered] == ["graph", "symbols"]
    assert external_stack.context_processor == ("processor", "context")

    registry.registered.clear()
    monkeypatch.setenv("CODECORTEX_BACKENDS", "auto")
    auto_stack = backend_factory.build_backend_stack(config, object())  # type: ignore[arg-type]
    assert auto_stack.active == ("graph", "context")
    assert [item.key for item in registry.registered] == ["graph"]

    specs["graph"].configured = False
    specs["context"].configured = False
    registry.registered.clear()
    assert backend_factory.build_backend_stack(config, object()).active == ()  # type: ignore[arg-type]


def test_language_registry_python_structural_native_and_types() -> None:
    registry = LanguageRegistry(native=False)
    assert registry.language_for(Path("thing.PY")) is not None
    assert registry.language_for(Path("thing.unknown")) is None
    assert registry.parse(Path("thing.unknown"), "x") == []
    assert registry.parse(Path("bad.py"), "def broken(:") == []

    source = """
class Child(Base):
    pass

def build(a: Child, /, b, *args, c, **kwargs) -> Child:
    return helper(a)

async def worker():
    await task()
"""
    units = registry.parse(Path("sample.py"), source)
    child = next(item for item in units if item.name == "Child")
    build = next(item for item in units if item.name == "build")
    worker = next(item for item in units if item.name == "worker")
    assert child.bases == ("Base",)
    assert build.kind == "function"
    assert build.signature == "(a, b, *c, *args, **kwargs)"
    assert build.return_type == "Child"
    assert build.annotations == {"a": "Child"}
    assert "helper" in build.references
    assert worker.kind == "async_function"

    js = registry._parse_structural(
        "javascript",
        "export class Widget extends Base {}\n"
        "export async function load(x): Result {\n"
        "const arrow = (x) => x;\n",
    )
    assert {item.name for item in js} >= {"Widget", "load", "arrow"}
    ruby = registry._parse_structural("ruby", "class Service\ndef run(x)\n")
    assert {item.name for item in ruby} == {"Service", "run"}
    go = registry._parse_structural("go", "func Run(x int) int {\n")
    assert go and go[0].name == "Run"
    assert len(registry._patterns("ruby")) == 2
    assert len(registry._patterns("typescript")) == 4
    assert len(registry._patterns("go")) == 3

    class _Native:
        def parse(self, language: str, text: str) -> list[Any]:
            return [
                SimpleNamespace(
                    name="Native",
                    kind="class",
                    line=1,
                    end_line=2,
                    signature=None,
                    return_type=None,
                    bases=("Base",),
                    references=("Ref",),
                )
            ]

    registry.native = _Native()  # type: ignore[assignment]
    native_units = registry.parse(Path("native.ts"), "class Native {}")
    assert native_units[0].name == "Native" and native_units[0].bases == ("Base",)

    class _BrokenNative:
        def parse(self, language: str, text: str) -> list[Any]:
            raise RuntimeError("parser failed")

    registry.native = _BrokenNative()  # type: ignore[assignment]
    fallback = registry.parse(Path("fallback.js"), "function fallback() {}")
    assert fallback[0].name == "fallback"

    resolved = registry.resolve_types(
        [
            ParsedUnit("Base", "class", 1),
            ParsedUnit(
                "Child",
                "class",
                2,
                bases=("Base",),
                annotations={"x": "Base | None"},
                return_type="Base",
            ),
        ]
    )
    assert resolved["Base"] == set()
    assert resolved["Child"] == {"Base"}

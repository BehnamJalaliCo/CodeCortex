"""Discover dependencies and their declared/resolved versions from manifests.

Every parser is defensive: a manifest that cannot be understood produces a
:class:`ManifestReport` explaining why, never an exception and never a silently
wrong version. Files are size-bounded so a hostile or generated manifest cannot
exhaust memory.
"""

from __future__ import annotations

import json
import re
import tomllib
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

from codecortex.dependencies.models import (
    DependencyRecord,
    DependencyScope,
    Ecosystem,
    ManifestReport,
)

#: Manifests larger than this are reported as unparsed rather than loaded.
MAX_MANIFEST_BYTES = 8 * 1024 * 1024

#: Directories never scanned for manifests.
SKIPPED_DIRECTORIES = frozenset(
    {
        ".git",
        ".codecortex",
        "node_modules",
        "vendor",
        "target",
        "dist",
        "build",
        ".venv",
        "venv",
        "__pycache__",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
    }
)

#: How deep below the project root manifests are searched for.
MAX_SCAN_DEPTH = 4

_PEP508_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(\[[^\]]*\])?\s*(.*)$")
_REQUIREMENT_SKIP = ("-r", "--", "#", "-c", "-e", ".", "/")
_GO_REQUIRE = re.compile(r"^\s*(?:require\s+)?([^\s()]+/[^\s()]+|[^\s()]+\.[^\s()]+)\s+(v[^\s/]+)")
_GRADLE = re.compile(
    r"""["']([A-Za-z0-9._-]+):([A-Za-z0-9._-]+):([A-Za-z0-9._+-]+)["']"""
)
_YAML_LOCK_ENTRY = re.compile(r"^\s{2,}(?:')?([^'\s:]+)(?:')?:\s*$")
_YAML_VERSION = re.compile(r"^\s+version:\s*(?:'|\")?([^'\"\s]+)")
_YARN_ENTRY = re.compile(r'^"?((?:@[^/\s"]+/)?[^@\s"]+)@[^:]*"?.*:$')
_YARN_VERSION = re.compile(r'^\s+"?version"?:?\s+"?([^"\s]+)"?')


@dataclass(frozen=True, slots=True)
class _ParsedManifest:
    records: tuple[DependencyRecord, ...]
    report: ManifestReport


def _read_text(path: Path) -> str | None:
    try:
        if path.stat().st_size > MAX_MANIFEST_BYTES:
            return None
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _split_requirement(value: str) -> tuple[str, str | None] | None:
    match = _PEP508_NAME.match(value)
    if match is None:
        return None
    name = match.group(1)
    remainder = (match.group(3) or "").split(";")[0].strip()
    return name, remainder or None


def _iter_manifest_files(root: Path) -> Iterator[Path]:
    """Yield candidate manifest files without descending into vendored trees."""
    stack: list[tuple[Path, int]] = [(root, 0)]
    while stack:
        directory, depth = stack.pop()
        try:
            entries = sorted(directory.iterdir())
        except OSError:
            continue
        for entry in entries:
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir():
                    if depth < MAX_SCAN_DEPTH and entry.name not in SKIPPED_DIRECTORIES:
                        stack.append((entry, depth + 1))
                    continue
            except OSError:  # pragma: no cover - transient filesystem races
                continue
            yield entry


class ManifestScanner:
    """Read every supported manifest under a project root."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def scan(self) -> tuple[tuple[DependencyRecord, ...], tuple[ManifestReport, ...]]:
        records: list[DependencyRecord] = []
        reports: list[ManifestReport] = []
        for path in _iter_manifest_files(self.root):
            parsed = self._parse(path)
            if parsed is None:
                continue
            records.extend(parsed.records)
            reports.append(parsed.report)
        return tuple(records), tuple(reports)

    def _relative(self, path: Path) -> str:
        try:
            return path.relative_to(self.root).as_posix()
        except ValueError:  # pragma: no cover - iteration stays under the root
            return path.name

    def _parse(self, path: Path) -> _ParsedManifest | None:
        name = path.name
        handlers: dict[str, tuple[Ecosystem, object]] = {
            "pyproject.toml": (Ecosystem.PYTHON, self._pyproject),
            "poetry.lock": (Ecosystem.PYTHON, self._poetry_lock),
            "uv.lock": (Ecosystem.PYTHON, self._uv_lock),
            "Pipfile": (Ecosystem.PYTHON, self._pipfile),
            "Pipfile.lock": (Ecosystem.PYTHON, self._pipfile_lock),
            "package.json": (Ecosystem.NODE, self._package_json),
            "package-lock.json": (Ecosystem.NODE, self._package_lock),
            "pnpm-lock.yaml": (Ecosystem.NODE, self._pnpm_lock),
            "yarn.lock": (Ecosystem.NODE, self._yarn_lock),
            "Cargo.toml": (Ecosystem.RUST, self._cargo_toml),
            "Cargo.lock": (Ecosystem.RUST, self._cargo_lock),
            "go.mod": (Ecosystem.GO, self._go_mod),
            "go.sum": (Ecosystem.GO, self._go_sum),
            "pom.xml": (Ecosystem.JVM, self._pom),
            "build.gradle": (Ecosystem.JVM, self._gradle),
            "build.gradle.kts": (Ecosystem.JVM, self._gradle),
            "packages.lock.json": (Ecosystem.DOTNET, self._packages_lock),
            "Directory.Packages.props": (Ecosystem.DOTNET, self._props),
        }
        handler = handlers.get(name)
        if handler is None:
            if name.endswith(".csproj"):
                handler = (Ecosystem.DOTNET, self._csproj)
            elif name == "requirements.txt" or (
                name.endswith(".txt") and path.parent.name == "requirements"
            ):
                handler = (Ecosystem.PYTHON, self._requirements)
            else:
                return None
        ecosystem, parser = handler
        relative = self._relative(path)
        text = _read_text(path)
        if text is None:
            return _ParsedManifest(
                (),
                ManifestReport(relative, ecosystem, False, "unreadable or oversized manifest"),
            )
        try:
            records = tuple(parser(text, relative))  # type: ignore[operator]
        except (ValueError, KeyError, TypeError, ElementTree.ParseError) as exc:
            return _ParsedManifest(
                (), ManifestReport(relative, ecosystem, False, f"malformed manifest: {exc}")
            )
        return _ParsedManifest(
            records, ManifestReport(relative, ecosystem, True, dependencies=len(records))
        )

    # -- Python -------------------------------------------------------------

    def _pyproject(self, text: str, manifest: str) -> Iterable[DependencyRecord]:
        data = tomllib.loads(text)
        project = data.get("project")
        if isinstance(project, dict):
            for item in project.get("dependencies", []) or []:
                parsed = _split_requirement(str(item))
                if parsed:
                    yield DependencyRecord(
                        Ecosystem.PYTHON, parsed[0], parsed[1], manifest=manifest
                    )
            optional = project.get("optional-dependencies")
            if isinstance(optional, dict):
                for group, items in optional.items():
                    for item in items or []:
                        parsed = _split_requirement(str(item))
                        if parsed:
                            yield DependencyRecord(
                                Ecosystem.PYTHON,
                                parsed[0],
                                parsed[1],
                                manifest=manifest,
                                scope=DependencyScope.DEVELOPMENT
                                if group in {"dev", "test", "tests"}
                                else DependencyScope.OPTIONAL,
                            )
        poetry = data.get("tool", {}).get("poetry", {}) if isinstance(data.get("tool"), dict) else {}
        if isinstance(poetry, dict):
            for key, scope in (
                ("dependencies", DependencyScope.RUNTIME),
                ("dev-dependencies", DependencyScope.DEVELOPMENT),
            ):
                section = poetry.get(key)
                if not isinstance(section, dict):
                    continue
                for name, spec in section.items():
                    if name == "python":
                        continue
                    declared = spec if isinstance(spec, str) else None
                    if isinstance(spec, dict):
                        version = spec.get("version")
                        declared = version if isinstance(version, str) else None
                    yield DependencyRecord(
                        Ecosystem.PYTHON, str(name), declared, manifest=manifest, scope=scope
                    )

    def _requirements(self, text: str, manifest: str) -> Iterable[DependencyRecord]:
        scope = (
            DependencyScope.DEVELOPMENT
            if any(token in manifest.lower() for token in ("dev", "test"))
            else DependencyScope.RUNTIME
        )
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if not line or line.startswith(_REQUIREMENT_SKIP):
                continue
            parsed = _split_requirement(line)
            if parsed:
                yield DependencyRecord(
                    Ecosystem.PYTHON, parsed[0], parsed[1], manifest=manifest, scope=scope
                )

    def _poetry_lock(self, text: str, manifest: str) -> Iterable[DependencyRecord]:
        for package in tomllib.loads(text).get("package", []) or []:
            if isinstance(package, dict) and package.get("name"):
                yield DependencyRecord(
                    Ecosystem.PYTHON,
                    str(package["name"]),
                    resolved=str(package.get("version")) if package.get("version") else None,
                    manifest=manifest,
                    lock_source=manifest,
                )

    _uv_lock = _poetry_lock

    def _pipfile(self, text: str, manifest: str) -> Iterable[DependencyRecord]:
        data = tomllib.loads(text)
        for key, scope in (
            ("packages", DependencyScope.RUNTIME),
            ("dev-packages", DependencyScope.DEVELOPMENT),
        ):
            section = data.get(key)
            if not isinstance(section, dict):
                continue
            for name, spec in section.items():
                declared = spec if isinstance(spec, str) else None
                if isinstance(spec, dict) and isinstance(spec.get("version"), str):
                    declared = spec["version"]
                yield DependencyRecord(
                    Ecosystem.PYTHON,
                    str(name),
                    None if declared in {"*", None} else declared,
                    manifest=manifest,
                    scope=scope,
                )

    def _pipfile_lock(self, text: str, manifest: str) -> Iterable[DependencyRecord]:
        data = json.loads(text)
        for key, scope in (
            ("default", DependencyScope.RUNTIME),
            ("develop", DependencyScope.DEVELOPMENT),
        ):
            section = data.get(key)
            if not isinstance(section, dict):
                continue
            for name, spec in section.items():
                version = spec.get("version") if isinstance(spec, dict) else None
                yield DependencyRecord(
                    Ecosystem.PYTHON,
                    str(name),
                    resolved=str(version).lstrip("=") if version else None,
                    manifest=manifest,
                    lock_source=manifest,
                    scope=scope,
                )

    # -- Node ---------------------------------------------------------------

    def _package_json(self, text: str, manifest: str) -> Iterable[DependencyRecord]:
        data = json.loads(text)
        for key, scope in (
            ("dependencies", DependencyScope.RUNTIME),
            ("devDependencies", DependencyScope.DEVELOPMENT),
            ("peerDependencies", DependencyScope.OPTIONAL),
            ("optionalDependencies", DependencyScope.OPTIONAL),
        ):
            section = data.get(key)
            if not isinstance(section, dict):
                continue
            for name, constraint in section.items():
                yield DependencyRecord(
                    Ecosystem.NODE,
                    str(name),
                    str(constraint) if constraint else None,
                    manifest=manifest,
                    scope=scope,
                )

    def _package_lock(self, text: str, manifest: str) -> Iterable[DependencyRecord]:
        data = json.loads(text)
        packages = data.get("packages")
        if isinstance(packages, dict):
            for location, spec in packages.items():
                if not location.startswith("node_modules/") or not isinstance(spec, dict):
                    continue
                name = location.rsplit("node_modules/", 1)[-1]
                version = spec.get("version")
                if name and version:
                    yield DependencyRecord(
                        Ecosystem.NODE,
                        name,
                        resolved=str(version),
                        manifest=manifest,
                        lock_source=manifest,
                    )
            return
        legacy = data.get("dependencies")
        if isinstance(legacy, dict):
            for name, spec in legacy.items():
                version = spec.get("version") if isinstance(spec, dict) else None
                if version:
                    yield DependencyRecord(
                        Ecosystem.NODE,
                        str(name),
                        resolved=str(version),
                        manifest=manifest,
                        lock_source=manifest,
                    )

    def _pnpm_lock(self, text: str, manifest: str) -> Iterable[DependencyRecord]:
        """Extract resolved versions without taking on a YAML dependency.

        Only the ``name:``/``version:`` pairs of the importer sections are read;
        anything else in the document is ignored. This is deliberately narrow
        and reported as best-effort rather than a full YAML parse.
        """
        current: str | None = None
        for raw in text.splitlines():
            entry = _YAML_LOCK_ENTRY.match(raw)
            if entry is not None and not raw.strip().startswith(("version:", "specifier:")):
                current = entry.group(1)
                continue
            version = _YAML_VERSION.match(raw)
            if version is not None and current:
                yield DependencyRecord(
                    Ecosystem.NODE,
                    current,
                    resolved=version.group(1).split("(")[0],
                    manifest=manifest,
                    lock_source=manifest,
                )
                current = None

    def _yarn_lock(self, text: str, manifest: str) -> Iterable[DependencyRecord]:
        current: str | None = None
        for raw in text.splitlines():
            if not raw.strip() or raw.lstrip().startswith("#"):
                continue
            if not raw.startswith((" ", "\t")):
                entry = _YARN_ENTRY.match(raw.strip())
                current = entry.group(1) if entry else None
                continue
            version = _YARN_VERSION.match(raw)
            if version is not None and current:
                yield DependencyRecord(
                    Ecosystem.NODE,
                    current,
                    resolved=version.group(1),
                    manifest=manifest,
                    lock_source=manifest,
                )
                current = None

    # -- Rust ---------------------------------------------------------------

    def _cargo_toml(self, text: str, manifest: str) -> Iterable[DependencyRecord]:
        data = tomllib.loads(text)
        for key, scope in (
            ("dependencies", DependencyScope.RUNTIME),
            ("dev-dependencies", DependencyScope.DEVELOPMENT),
            ("build-dependencies", DependencyScope.BUILD),
        ):
            section = data.get(key)
            if not isinstance(section, dict):
                continue
            for name, spec in section.items():
                declared = spec if isinstance(spec, str) else None
                if isinstance(spec, dict) and isinstance(spec.get("version"), str):
                    declared = spec["version"]
                yield DependencyRecord(
                    Ecosystem.RUST, str(name), declared, manifest=manifest, scope=scope
                )

    def _cargo_lock(self, text: str, manifest: str) -> Iterable[DependencyRecord]:
        for package in tomllib.loads(text).get("package", []) or []:
            if isinstance(package, dict) and package.get("name"):
                yield DependencyRecord(
                    Ecosystem.RUST,
                    str(package["name"]),
                    resolved=str(package.get("version")) if package.get("version") else None,
                    manifest=manifest,
                    lock_source=manifest,
                )

    # -- Go -----------------------------------------------------------------

    def _go_mod(self, text: str, manifest: str) -> Iterable[DependencyRecord]:
        for raw in text.splitlines():
            line = raw.split("//", 1)[0]
            if line.strip().startswith(("module ", "go ", "toolchain ")):
                continue
            match = _GO_REQUIRE.match(line)
            if match is not None:
                yield DependencyRecord(
                    Ecosystem.GO, match.group(1), match.group(2), manifest=manifest
                )

    def _go_sum(self, text: str, manifest: str) -> Iterable[DependencyRecord]:
        seen: set[str] = set()
        for raw in text.splitlines():
            parts = raw.split()
            if len(parts) < 2 or parts[1].endswith("/go.mod"):
                continue
            if parts[0] in seen:
                continue
            seen.add(parts[0])
            yield DependencyRecord(
                Ecosystem.GO,
                parts[0],
                resolved=parts[1],
                manifest=manifest,
                lock_source=manifest,
            )

    # -- JVM and .NET -------------------------------------------------------

    @staticmethod
    def _safe_xml(text: str) -> ElementTree.Element:
        """Parse XML after rejecting documents that declare entities.

        Entity declarations are the vector for expansion attacks, and no
        supported build manifest needs them.
        """
        if "<!DOCTYPE" in text or "<!ENTITY" in text:
            raise ValueError("XML manifests with entity declarations are not parsed")
        return ElementTree.fromstring(text)  # nosec B314

    def _pom(self, text: str, manifest: str) -> Iterable[DependencyRecord]:
        root = self._safe_xml(text)
        properties: dict[str, str] = {}
        for element in root.iter():
            tag = element.tag.rsplit("}", 1)[-1]
            if tag == "properties":
                for child in element:
                    key = child.tag.rsplit("}", 1)[-1]
                    if child.text:
                        properties[key] = child.text.strip()
        for element in root.iter():
            if element.tag.rsplit("}", 1)[-1] != "dependency":
                continue
            fields = {
                child.tag.rsplit("}", 1)[-1]: (child.text or "").strip() for child in element
            }
            group = fields.get("groupId", "")
            artifact = fields.get("artifactId", "")
            version = fields.get("version") or None
            if version and version.startswith("${") and version.endswith("}"):
                version = properties.get(version[2:-1], version)
            if artifact:
                yield DependencyRecord(
                    Ecosystem.JVM,
                    f"{group}:{artifact}" if group else artifact,
                    version,
                    manifest=manifest,
                    scope=DependencyScope.DEVELOPMENT
                    if fields.get("scope") == "test"
                    else DependencyScope.RUNTIME,
                )

    def _gradle(self, text: str, manifest: str) -> Iterable[DependencyRecord]:
        seen: set[str] = set()
        for match in _GRADLE.finditer(text):
            name = f"{match.group(1)}:{match.group(2)}"
            if name in seen:
                continue
            seen.add(name)
            yield DependencyRecord(Ecosystem.JVM, name, match.group(3), manifest=manifest)

    def _csproj(self, text: str, manifest: str) -> Iterable[DependencyRecord]:
        for element in self._safe_xml(text).iter():
            if element.tag.rsplit("}", 1)[-1] != "PackageReference":
                continue
            name = element.get("Include") or element.get("Update")
            if name:
                yield DependencyRecord(
                    Ecosystem.DOTNET, name, element.get("Version"), manifest=manifest
                )

    def _props(self, text: str, manifest: str) -> Iterable[DependencyRecord]:
        for element in self._safe_xml(text).iter():
            if element.tag.rsplit("}", 1)[-1] != "PackageVersion":
                continue
            name = element.get("Include")
            if name:
                yield DependencyRecord(
                    Ecosystem.DOTNET, name, element.get("Version"), manifest=manifest
                )

    def _packages_lock(self, text: str, manifest: str) -> Iterable[DependencyRecord]:
        data = json.loads(text)
        for framework in (data.get("dependencies") or {}).values():
            if not isinstance(framework, dict):
                continue
            for name, spec in framework.items():
                resolved = spec.get("resolved") if isinstance(spec, dict) else None
                yield DependencyRecord(
                    Ecosystem.DOTNET,
                    str(name),
                    resolved=str(resolved) if resolved else None,
                    manifest=manifest,
                    lock_source=manifest,
                )

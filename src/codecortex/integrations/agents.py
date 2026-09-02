"""Merge-safe project configuration for MCP-capable coding agents."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any


class AgentTarget(StrEnum):
    CLAUDE = "claude"
    CODEX = "codex"
    CURSOR = "cursor"
    GEMINI = "gemini"
    OPENCODE = "opencode"


@dataclass(frozen=True, slots=True)
class AgentMutation:
    target: AgentTarget
    path: Path
    detected: bool
    changed: bool
    backup: Path | None = None
    detail: str = ""


class AgentConfigurationError(RuntimeError):
    pass


class AgentConfigurator:
    """Configure project-local integrations without clobbering user-owned settings."""

    COMMANDS = {
        AgentTarget.CLAUDE: ("claude",),
        AgentTarget.CODEX: ("codex",),
        AgentTarget.GEMINI: ("gemini",),
        AgentTarget.OPENCODE: ("opencode",),
    }

    def __init__(self, root: Path, *, executable: str = "cortex") -> None:
        self.root = root.expanduser().resolve()
        self.executable = executable

    def detect(self) -> tuple[AgentTarget, ...]:
        found: set[AgentTarget] = set()
        for target, commands in self.COMMANDS.items():
            if any(shutil.which(command) for command in commands):
                found.add(target)
        if (self.root / ".cursor").exists() or shutil.which("cursor"):
            found.add(AgentTarget.CURSOR)
        if (self.root / ".mcp.json").exists():
            found.add(AgentTarget.CLAUDE)
        if (self.root / ".gemini").exists():
            found.add(AgentTarget.GEMINI)
        if (self.root / ".codex").exists():
            found.add(AgentTarget.CODEX)
        if (self.root / "opencode.json").exists():
            found.add(AgentTarget.OPENCODE)
        return tuple(sorted(found, key=str))

    def configure(
        self,
        targets: tuple[AgentTarget, ...] | None = None,
        *,
        dry_run: bool = False,
    ) -> tuple[AgentMutation, ...]:
        selected = targets or self.detect()
        return tuple(self.configure_one(target, dry_run=dry_run) for target in selected)

    def configure_one(self, target: AgentTarget, *, dry_run: bool = False) -> AgentMutation:
        detected = target in self.detect()
        if target == AgentTarget.CLAUDE:
            return self._configure_json(
                target,
                self.root / ".mcp.json",
                ("mcpServers",),
                self._stdio_json(),
                detected,
                dry_run,
            )
        if target == AgentTarget.CURSOR:
            return self._configure_json(
                target,
                self.root / ".cursor" / "mcp.json",
                ("mcpServers",),
                self._stdio_json(),
                detected,
                dry_run,
            )
        if target == AgentTarget.GEMINI:
            return self._configure_json(
                target,
                self.root / ".gemini" / "settings.json",
                ("mcpServers",),
                self._stdio_json(),
                detected,
                dry_run,
            )
        if target == AgentTarget.OPENCODE:
            return self._configure_json(
                target,
                self.root / "opencode.json",
                ("mcp", "servers"),
                {
                    "type": "local",
                    "command": [self.executable, "mcp", "--path", str(self.root)],
                },
                detected,
                dry_run,
                defaults={"$schema": "https://opencode.ai/config.json"},
            )
        if target == AgentTarget.CODEX:
            return self._configure_codex(detected=detected, dry_run=dry_run)
        raise ValueError(target)

    def _stdio_json(self) -> dict[str, Any]:
        return {
            "command": self.executable,
            "args": ["mcp", "--path", str(self.root)],
            "env": {"CODECORTEX_BACKENDS": "auto"},
        }

    def _configure_json(
        self,
        target: AgentTarget,
        path: Path,
        container_keys: tuple[str, ...],
        server: dict[str, Any],
        detected: bool,
        dry_run: bool,
        *,
        defaults: dict[str, Any] | None = None,
    ) -> AgentMutation:
        payload: dict[str, Any] = dict(defaults or {})
        if path.exists():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise AgentConfigurationError(
                    f"refusing to modify invalid JSON: {path}: {exc}"
                ) from exc
            if not isinstance(loaded, dict):
                raise AgentConfigurationError(f"expected a JSON object: {path}")
            payload = loaded
            for key, value in (defaults or {}).items():
                payload.setdefault(key, value)
        container: dict[str, Any] = payload
        for key in container_keys:
            child = container.get(key)
            if child is None:
                child = {}
                container[key] = child
            if not isinstance(child, dict):
                raise AgentConfigurationError(
                    f"cannot merge CodeCortex into non-object {'.'.join(container_keys)} in {path}"
                )
            container = child
        previous = container.get("codecortex")
        container["codecortex"] = server
        changed = previous != server or not path.exists()
        if not changed or dry_run:
            return AgentMutation(
                target,
                path,
                detected,
                changed,
                detail="dry-run" if dry_run and changed else "already configured",
            )
        backup = self._backup(path)
        self._atomic_write(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        return AgentMutation(target, path, detected, True, backup=backup, detail="configured")

    def _configure_codex(self, *, detected: bool, dry_run: bool) -> AgentMutation:
        path = self.root / ".codex" / "config.toml"
        begin = "# >>> codecortex managed mcp >>>"
        end = "# <<< codecortex managed mcp <<<"
        args = ["mcp", "--path", str(self.root)]
        block = "\n".join(
            [
                begin,
                "[mcp_servers.codecortex]",
                f"command = {json.dumps(self.executable)}",
                f"args = {json.dumps(args)}",
                'env = { CODECORTEX_BACKENDS = "auto" }',
                "enabled = true",
                "startup_timeout_sec = 30",
                "tool_timeout_sec = 120",
                end,
            ]
        )
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        managed = re.compile(re.escape(begin) + r".*?" + re.escape(end), re.DOTALL)
        if managed.search(existing):
            # A callable replacement keeps Windows backslashes literal instead of
            # letting re.sub interpret them as replacement-string escapes.
            updated = managed.sub(lambda _match: block, existing)
        else:
            if re.search(r"(?m)^\s*\[mcp_servers\.codecortex\]\s*$", existing):
                raise AgentConfigurationError(
                    f"refusing to overwrite an unmanaged [mcp_servers.codecortex] table in {path}"
                )
            separator = "\n\n" if existing.strip() else ""
            updated = existing.rstrip() + separator + block + "\n"
        changed = updated != existing
        if not changed or dry_run:
            return AgentMutation(
                AgentTarget.CODEX,
                path,
                detected,
                changed,
                detail="dry-run" if dry_run and changed else "already configured",
            )
        backup = self._backup(path)
        self._atomic_write(path, updated)
        return AgentMutation(
            AgentTarget.CODEX, path, detected, True, backup=backup, detail="configured"
        )

    @staticmethod
    def _backup(path: Path) -> Path | None:
        if not path.exists():
            return None
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
        backup = path.with_name(f"{path.name}.codecortex-{stamp}.bak")
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup)
        return backup

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        except Exception:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
            raise

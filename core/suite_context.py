"""Isolated suite context and path policy."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SuiteContext:
    suite_dir: Path
    workspace: Path

    @classmethod
    def create(cls, suite_dir: str | Path, workspace: str | Path) -> "SuiteContext":
        suite = Path(suite_dir).resolve()
        ws = Path(workspace).resolve()
        if not (suite / "suite.yaml").is_file():
            raise ValueError(f"suite.yaml not found: {suite}")
        try:
            suite.relative_to(ws / "suites")
        except ValueError as exc:
            raise ValueError(f"suite must be under {ws / 'suites'}: {suite}") from exc
        return cls(suite, ws)

    def resolve(self, value: str | Path, *, allow_workspace_shared: bool = False) -> Path:
        path = Path(value)
        if not path.is_absolute():
            path = self.suite_dir / path
        path = path.resolve()
        roots = [self.suite_dir]
        if allow_workspace_shared:
            roots.append(self.workspace)
        if not any(_within(path, root) for root in roots):
            raise ValueError(f"path escapes suite context: {path}")
        return path


def _within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False

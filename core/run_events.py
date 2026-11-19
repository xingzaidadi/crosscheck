"""Append-only run event facts used by reports, recovery, and audit."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def append_event(run_dir: str | Path, *, run_id: str, case_id: str = "", step_id: str = "",
                 state: str, failure_class: str = "", evidence_refs: list[str] | None = None,
                 assertion_ids: list[str] | None = None, detail: str = "", **extra: Any) -> Path:
    root = Path(run_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = root / "events.jsonl"
    event = {
        "schema_version": 1,
        "run_id": run_id,
        "case_id": case_id,
        "step_id": step_id,
        "state": state,
        "failure_class": failure_class,
        "evidence_refs": evidence_refs or [],
        "assertion_ids": assertion_ids or [],
        "detail": detail,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        **extra,
    }
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
    return path


def read_events(run_dir: str | Path) -> list[dict[str, Any]]:
    path = Path(run_dir) / "events.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

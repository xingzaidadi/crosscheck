"""Conservative knowledge-first matching for canonical expectations."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


_APPROVED = {"human_verified", "approved", "verified"}
_VISIBILITY_TERMS = ("可见", "显示", "隐藏", "按钮", "页签", "弹窗")


def _tokens(value: str) -> set[str]:
    return {item.lower() for item in re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{2,}", value or "")}


def _approved_query_mapping(workspace: Path, feature: str) -> dict[str, Any] | None:
    if not feature:
        return None
    path = workspace / "knowledge_base" / "query_mapping" / f"{feature}.json"
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if str(value.get("verify_status") or "").lower() not in _APPROVED:
        return None
    value["_path"] = str(path)
    return value


def _mapped_display_labels(ui: dict[str, Any]) -> set[str]:
    labels = set()
    extract = ui.get("extract") or {}
    labels.update(str(item) for item in (extract.get("columns") or {}))
    labels.update(str(item) for item in (ui.get("dom_to_api") or {}))
    labels.update(str(item) for item in (extract.get("dom_to_api") or {}))
    return {item for item in labels if item}


def match_assertion_knowledge(
    case: dict[str, Any], spec, workspace: str | Path, assertion_texts: dict[str, str]
) -> dict[str, Any]:
    """Bind only expectations directly supported by approved assets and runtime proofs."""
    workspace_path = Path(workspace).resolve()
    ui = spec.ui or {}
    mapping = _approved_query_mapping(workspace_path, str(spec.feature or ""))
    display_labels = _mapped_display_labels(ui)
    bindings: dict[str, dict[str, str]] = {}
    dependencies: list[dict[str, str]] = []
    candidates: list[dict[str, Any]] = []
    for assertion_id, text in assertion_texts.items():
        tokens = _tokens(text)
        binding = None
        source = ""
        if ui.get("visibility_asserts") and any(term in text for term in _VISIBILITY_TERMS):
            binding = {"layer": "ui", "proof": "ui_check", "ref": "ui.visibility_asserts"}
            source = str((spec.raw or {}).get("binding_path") or "")
        elif ui.get("value_asserts") and any(term in text for term in ("数量", "金额", "总数", "值", "状态")):
            binding = {"layer": "ui", "proof": "ui_check", "ref": "ui.value_asserts"}
            source = str((spec.raw or {}).get("binding_path") or "")
        elif ui.get("field_asserts") and any(term in text for term in ("字段", "只读", "带出", "为空")):
            binding = {"layer": "ui", "proof": "ui_check", "ref": "ui.field_asserts"}
            source = str((spec.raw or {}).get("binding_path") or "")
        elif ui.get("extract") and mapping:
            mentioned_labels = {label for label in display_labels if label in text}
            if mentioned_labels:
                binding = {"layer": "ui", "proof": "ui_check", "ref": "ui.extract"}
                source = str(mapping["_path"])
        if binding:
            bindings[assertion_id] = binding
            if source and not any(item["source"] == source for item in dependencies):
                dependencies.append({"kind": "approved_asset", "source": source})
        else:
            candidates.append({"assertion_id": assertion_id, "text": text, "status": "UNMATCHED"})
    return {"bindings": bindings, "dependencies": dependencies, "candidates": candidates}

"""Evidence-bound UI oracle evaluation."""
from __future__ import annotations

from typing import Any

from core.ui_test_intake import UiOracle
from scripts.ui_test import _evaluate_oracle


def enrich_oracles(oracles: list[dict], instruction: str) -> list[dict]:
    enriched = [dict(item) for item in oracles]
    lowered = instruction.lower()
    if any(term in lowered for term in ("只读", "不可编辑", "read only", "readonly")) \
            and not any(item.get("kind") == "readonly" for item in enriched):
        enriched.append(UiOracle("readonly", "page", True, "semantic readonly intent").to_dict())
    if any(term in lowered for term in ("正常", "可用", "健康", "成功打开", "能打开")) \
            and not any(item.get("kind") == "page_health" for item in enriched):
        enriched.append({
            "kind": "page_health", "value": "page", "expected": True,
            "source": "semantic page health intent", "fields": [],
        })
    return enriched


def verify(page, oracles: list[dict], instruction: str) -> list[dict[str, Any]]:
    return [_evaluate_oracle(page, item) for item in enrich_oracles(oracles, instruction)]

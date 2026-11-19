"""Pure helpers for deriving safe, read-only UI action candidates."""
from __future__ import annotations

import re
from typing import Any


SAFE_LABELS = (
    "查询", "搜索", "筛选", "详情", "明细查询", "整单查询", "全部", "刷新", "返回",
    "下一页", "上一页", "关闭", "展开", "收起",
)


def extract_safe_labels(text: str) -> list[str]:
    """Return short, visible labels that are safe to probe without mutation."""
    value = str(text or "")
    found: dict[int, str] = {}
    for label in SAFE_LABELS:
        start = value.find(label)
        if start >= 0:
            found[start] = label
    for match in re.finditer(
        r"(?:点击|选择|打开|切换|查看)\s*[“『「]?([^”』」\s，。,；;]+)", value
    ):
        label = re.sub(r"(并|然后|再).*$", "", match.group(1)).strip()
        if label in SAFE_LABELS:
            found[match.start(1)] = label
    ordered = [label for _, label in sorted(found.items())]
    return [label for label in dict.fromkeys(ordered)
            if not any(label != other and label in other for other in ordered)]


def build_action_candidates(text: str, body_text: str) -> list[dict[str, Any]]:
    """Map expectation/action language to visible text candidates, never executable by itself."""
    requested = extract_safe_labels(text)
    visible = str(body_text or "")
    return [
        {"action": "click", "text": label, "visible": label in visible,
         "state": "candidate", "requires_replay": True}
        for label in requested
    ]

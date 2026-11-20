"""Deterministic semantic normalization for autonomous UI planning."""
from __future__ import annotations

import re


ALIASES = (
    {"待处理", "处理中", "pending", "to do"},
    {"详情页", "详情", "明细", "detail"},
    {"查询", "搜索", "筛选", "search", "query", "filter"},
    {"返回", "后退", "back"},
    {"首条", "第一条", "第一行", "first record"},
)


def normalize(value: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", str(value or "").lower())


def equivalent(value: str, target: str) -> bool:
    left = normalize(value)
    right = normalize(target)
    if not left or not right:
        return False
    if left == right or left in right or right in left:
        return True
    for group in ALIASES:
        aliases = {normalize(item) for item in group}
        if any(alias in left for alias in aliases) and any(alias in right for alias in aliases):
            return True
    return False

"""唯一标记值:所有造数带 AUTOTEST_ 前缀,用于隔离 + 清理 + diff 排除。"""
from __future__ import annotations

import time


def make_marker(case_id: str) -> str:
    """AUTOTEST_{case_id}_{时间戳}。全局唯一,贯穿造数/校验/清理。"""
    return f"AUTOTEST_{case_id}_{int(time.time() * 1000)}"


def is_marker(value: str) -> bool:
    return isinstance(value, str) and value.startswith("AUTOTEST_")

"""Deterministic semantic normalization for autonomous UI planning."""
from __future__ import annotations

import re


# 通用 UI 动作/导航同义词组。只收**通用交互词**,不收任何业务领域词
# (业务词由 workspace/用例/契约文本派生,受 tests/test_no_business_in_core.py 守卫)。
# 同一组内的措辞被视为可互换目标:用例说"下单"、按钮叫"提交"仍能对上。
ALIASES = (
    {"待处理", "处理中", "pending", "to do"},
    {"详情页", "详情", "明细", "查看详情", "detail", "view detail"},
    {"查询", "搜索", "筛选", "检索", "search", "query", "filter"},
    {"返回", "后退", "上一步", "back", "previous"},
    {"首条", "第一条", "第一行", "first record", "first row"},
    {"提交", "保存", "确定", "确认", "下单", "submit", "save", "confirm", "ok"},
    {"新增", "新建", "创建", "添加", "add", "new", "create"},
    {"编辑", "修改", "更新", "edit", "modify", "update"},
    {"取消", "关闭", "cancel", "close"},
    {"重置", "清空", "reset", "clear"},
    {"下一步", "继续", "next", "continue"},
    {"导出", "下载", "export", "download"},
    {"上传", "导入", "upload", "import"},
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

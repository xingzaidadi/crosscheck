"""
应用知识库(大脑):加载 / 查询 / 回写。

四部分:page_model(怎么操作)、data_mapping(功能→库/表/字段)、
business_rules(PRD 规则)、invalid_input_rules(非法输入通用模板)。

执行只信 verify_status == "human_verified";auto_discovered_pending 走 diff 兜底 + 标记待审。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class KnowledgeBase:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self._page_model: dict[str, dict] = {}
        self._data_mapping: dict[str, dict] = {}
        self._business_rules: list[dict] = []
        self._invalid_input_rules: list[dict] = []

    def load(self) -> "KnowledgeBase":
        """从磁盘加载全部知识(JSON/YAML + Git 版本控制)。"""
        # TODO: 遍历 page_model/ data_mapping/ 下每个功能一个文件,按 feature 建索引
        # TODO: 读 business_rules.json / invalid_input_rules.json
        return self

    def page_model(self, feature: str) -> dict[str, Any]:
        """取某功能的页面模型(entry/dialog/fields/submit/auth/success_indicator/api)。"""
        # TODO
        return self._page_model.get(feature, {})

    def data_mapping(self, feature: str) -> dict[str, Any]:
        """取某功能的库/表/字段映射。执行器用它做兜底校验与 diff 预期。"""
        # TODO
        return self._data_mapping.get(feature, {})

    def write_back_pending(self, feature: str, discovered: dict) -> None:
        """回写新发现的映射/规则,verify_status 标 auto_discovered_pending 待审。"""
        # TODO: 落盘 + 走 Git,等人审转 human_verified
        ...

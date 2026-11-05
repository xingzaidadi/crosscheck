"""
自进化字段知识库:每个功能一份 <workspace>/knowledge_base/field_intel/<feature>.json。
攒"某功能的表单字段怎么填":标签/选择器/控件类型/是否必填/合法值/样例值/填写顺序/出处/置信度。

进化闭环:
  1. load()  —— 执行前先读已知,能秒填就秒填;
  2. merge() —— 探测器(前端/库/文档)新发现的字段 upsert 进来(按出处权重取优),置信度累积;
  3. record()—— 回放命中/失效记账,失效多了标记需重探(页面变了自动重学);
不同功能各一份,互不干扰;知识是业务数据,落 workspace(不进框架仓库)。
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from core.workspace import kb_dir

# 出处权重:人工 > 文档(业务口径) > 库(枚举/约束) > 前端(控件/校验)
_SRC_WEIGHT = {"manual": 100, "docs": 70, "db": 60, "frontend": 50, "": 0}
_STALE_MISS = 3   # 连续/累计失效达到此数,判该字段需重探


class FieldIntel:
    def __init__(self, feature: str):
        self.feature = feature
        self.path = kb_dir() / "field_intel" / f"{feature}.json"
        self.data: dict[str, Any] = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                pass
        return {"feature": self.feature, "updated_at": "", "fields": {}, "fill_order": [], "notes": []}

    @property
    def fields(self) -> dict:
        return self.data["fields"]

    def known(self) -> bool:
        """已有可用字段知识(可先尝试秒填)。"""
        return bool(self.data["fields"])

    def required_fields(self) -> list[str]:
        return [k for k, f in self.fields.items() if f.get("required")]

    def merge(self, discovered: list[dict], source: str) -> None:
        """upsert 新发现的字段。discovered: [{key/label, selector, control, required, options, format, value_hint}]。"""
        w = _SRC_WEIGHT.get(source, 0)
        for d in discovered:
            key = d.get("key") or d.get("label")
            if not key:
                continue
            cur = self.fields.get(key, {"source": "", "confidence": 0, "hits": 0, "misses": 0})
            cw = _SRC_WEIGHT.get(cur.get("source", ""), 0)
            # 高权重出处可覆盖已有属性;否则只补空
            for attr in ("label", "selector", "control", "format", "value_hint"):
                v = d.get(attr)
                if v not in (None, "") and (w >= cw or not cur.get(attr)):
                    cur[attr] = v
            if d.get("required"):
                cur["required"] = True              # 任一来源说必填即必填
            if d.get("options"):
                cur["options"] = sorted(set((cur.get("options") or []) + list(d["options"])))
            if w >= cw:
                cur["source"] = source
            cur["confidence"] = max(cur.get("confidence", 0), w)
            self.fields[key] = cur
            if key not in self.data["fill_order"]:
                self.data["fill_order"].append(key)

    def record(self, key: str, ok: bool) -> None:
        """回放记账:命中 hits+1,失效 misses+1;失效多了标 stale 需重探。"""
        f = self.fields.get(key)
        if not f:
            return
        if ok:
            f["hits"] = f.get("hits", 0) + 1
            f["misses"] = 0
            f["stale"] = False
        else:
            f["misses"] = f.get("misses", 0) + 1
            if f["misses"] >= _STALE_MISS:
                f["stale"] = True       # 页面大概变了,下次重探此字段

    def stale_fields(self) -> list[str]:
        return [k for k, f in self.fields.items() if f.get("stale")]

    def note(self, text: str) -> None:
        if text and text not in self.data["notes"]:
            self.data["notes"].append(text)

    def save(self) -> Path:
        self.data["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        return self.path

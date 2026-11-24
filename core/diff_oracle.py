"""差异测试 oracle(通用、零业务):旧系统即 oracle。

迁移/回归场景里,人写断言成本高又易漏;但"旧系统的输出"本身就是最权威的 oracle。
本模块对同一请求,比对 baseline(旧)与 candidate(新)的响应体 + 库行,逐字段报差异,
天然不需要人工写期望值——这是现在完全缺失、对系统重构验证价值极高的差异化能力。

纯函数、确定性、不碰网络/库(取数的脏活由调用方喂进来),便于单测与复算。
支持 ignore_paths(时间戳/自增 id 等易变字段白名单),避免噪声误报。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.verifier import _dig, _eq, _MISSING


@dataclass
class FieldDiff:
    path: str
    baseline: Any
    candidate: Any

    def to_dict(self) -> dict[str, Any]:
        def _s(v: Any) -> Any:
            return None if v is _MISSING else v
        return {"path": self.path, "baseline": _s(self.baseline), "candidate": _s(self.candidate)}


@dataclass
class DiffResult:
    consistent: bool
    diffs: list[FieldDiff] = field(default_factory=list)
    compared_paths: list[str] = field(default_factory=list)
    ignored: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "consistent": self.consistent,
            "diff_count": len(self.diffs),
            "diffs": [d.to_dict() for d in self.diffs],
            "compared_paths": self.compared_paths,
            "ignored": self.ignored,
        }


def _flatten(obj: Any, prefix: str = "") -> dict[str, Any]:
    """把嵌套 dict/list 展平成点路径 → 叶子值,便于逐字段比对。"""
    out: dict[str, Any] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(_flatten(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.update(_flatten(v, f"{prefix}.{i}"))
    else:
        out[prefix] = obj
    return out


def _ignored(path: str, ignore_paths: set[str]) -> bool:
    for ig in ignore_paths:
        if path == ig or path.startswith(ig + ".") or path.endswith("." + ig):
            return True
        # 列表下标通配:ignore "list.updateTime" 命中 "list.0.updateTime"
        segs = path.split(".")
        if ig in segs:
            return True
    return False


def diff_payloads(baseline: Any, candidate: Any, *,
                  ignore_paths: set[str] | None = None) -> DiffResult:
    """比对两份响应体(或两组库行),逐叶子字段报差异。"""
    ignore_paths = set(ignore_paths or [])
    flat_b = _flatten(baseline)
    flat_c = _flatten(candidate)
    all_paths = sorted(set(flat_b) | set(flat_c))
    diffs: list[FieldDiff] = []
    compared: list[str] = []
    ignored: list[str] = []
    for p in all_paths:
        if _ignored(p, ignore_paths):
            ignored.append(p)
            continue
        bv = flat_b.get(p, _MISSING)
        cv = flat_c.get(p, _MISSING)
        compared.append(p)
        if bv is _MISSING or cv is _MISSING:
            if not (bv is _MISSING and cv is _MISSING):
                diffs.append(FieldDiff(p, bv, cv))
        elif not _eq(bv, cv):
            diffs.append(FieldDiff(p, bv, cv))
    return DiffResult(consistent=not diffs, diffs=diffs,
                      compared_paths=compared, ignored=ignored)


def diff_selected(baseline: dict[str, Any], candidate: dict[str, Any], *,
                  paths: list[str], ignore_paths: set[str] | None = None) -> DiffResult:
    """只比对指定点路径(响应字段抽样),其余忽略。用于大响应的定向对账。"""
    ignore_paths = set(ignore_paths or [])
    diffs: list[FieldDiff] = []
    compared: list[str] = []
    for p in paths:
        if _ignored(p, ignore_paths):
            continue
        bv = _dig(baseline, p)
        cv = _dig(candidate, p)
        compared.append(p)
        if bv is _MISSING or cv is _MISSING:
            if not (bv is _MISSING and cv is _MISSING):
                diffs.append(FieldDiff(p, bv, cv))
        elif not _eq(bv, cv):
            diffs.append(FieldDiff(p, bv, cv))
    return DiffResult(consistent=not diffs, diffs=diffs,
                      compared_paths=compared, ignored=sorted(ignore_paths))

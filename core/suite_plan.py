"""Plan a test suite before execution: identity, intent, required layers and gaps."""
from __future__ import annotations

import hashlib
import html
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


_UI = re.compile(r"页面|页签|按钮|展示|显示|输入|点击|切换|弹窗|前端|UI|浏览器", re.I)
_API = re.compile(r"接口|API|HTTP|请求|响应|调用\s*(GET|POST|PUT|DELETE)|/[\w.-]+/api/", re.I)
_DB = re.compile(r"数据库|查库|落库|表\b|字段|SQL|记录表|唯一索引|审计字段|数据一致", re.I)
_WRITE = re.compile(r"新增|创建|提交|保存|修改|删除|审批|转办|退回|关闭|撤回|下单|发起")
_QUERY = re.compile(r"查询|搜索|筛选|列表|分页|统计|角标|页签|展示|查看|详情")
_PERMISSION = re.compile(r"权限|角色|数据隔离|可见|不可见|越权|账号")
_WORKFLOW = re.compile(r"状态|流转|节点|审批|按钮链|前置|处理中|完成|退回|转办")
_NEGATIVE = re.compile(r"拒绝|拦截|不允许|不可|不能|异常|错误|边界|无权限|不出现")


def _case_text(raw: Any) -> str:
    return "\n".join(str(getattr(raw, field, "") or "") for field in (
        "name", "module", "tags", "preconditions", "notes", "steps_text", "expected_text"
    ))


def suite_fingerprint(raws: list[Any]) -> str:
    """Stable identity that changes when case IDs are reused with different semantics."""
    rows = [f"{raw.case_id}\t{raw.name.strip()}\t{getattr(raw, 'module', '').strip()}" for raw in raws]
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()[:16]


def classify_case(raw: Any) -> dict[str, Any]:
    text = _case_text(raw)
    intents = []
    for name, pattern in (
        ("permission", _PERMISSION), ("workflow", _WORKFLOW), ("negative", _NEGATIVE),
        ("write", _WRITE), ("query", _QUERY),
    ):
        if pattern.search(text):
            intents.append(name)
    if not intents:
        intents.append("other")

    required = []
    if _UI.search(text):
        required.append("ui")
    if _API.search(text):
        required.append("api")
    if _DB.search(text):
        required.append("db")
    if not required:
        if "write" in intents:
            required = ["api", "db"]
        elif "query" in intents:
            required = ["api"]
        else:
            required = ["manual"]

    priority = str(getattr(raw, "level", "") or "").upper()
    return {
        "case_id": raw.case_id,
        "title": raw.name,
        "module": getattr(raw, "category", "") or getattr(raw, "module", ""),
        "priority": priority,
        "intents": intents,
        "required_layers": required,
        "three_layer_required": all(layer in required for layer in ("ui", "api", "db")),
    }


def _provided_layers(spec: Any) -> list[str]:
    if spec.verify_status != "human_verified":
        return []
    layers = []
    if spec.mode == "ui" or spec.ui:
        layers.append("ui")
    if spec.mode in ("api", "write", "reconcile") or spec.request or (spec.ui or {}).get("url_pattern"):
        layers.append("api")
    if spec.mode == "reconcile" or (spec.assertions or {}).get("db") or (
        spec.mode == "ui" and getattr(spec, "db", "") and getattr(spec, "feature", "")
    ):
        layers.append("db")
    if spec.mode == "script":
        layers.append("script")
    return list(dict.fromkeys(layers))


def build_suite_plan(raws: list[Any], specs: list[Any], source: str = "") -> dict[str, Any]:
    by_id = {spec.case_id: spec for spec in specs}
    cases = []
    for raw in raws:
        item = classify_case(raw)
        spec = by_id.get(raw.case_id)
        provided = _provided_layers(spec) if spec else []
        missing = [layer for layer in item["required_layers"] if layer not in provided]
        review = list(getattr(spec, "needs_review", []) or []) if spec else ["未生成规格"]
        item.update({
            "provided_layers": provided,
            "missing_layers": missing,
            "mode": getattr(spec, "mode", "") if spec else "",
            "verify_status": getattr(spec, "verify_status", "") if spec else "",
            "blocked": getattr(spec, "blocked", "") if spec else "",
            "needs_review": review,
            "executable": bool(spec and spec.verify_status == "human_verified" and not spec.blocked and not missing),
        })
        cases.append(item)

    required_counts = Counter(layer for case in cases for layer in case["required_layers"])
    provided_counts = Counter(layer for case in cases for layer in case["provided_layers"])
    intent_counts = Counter(intent for case in cases for intent in case["intents"])
    return {
        "suite_id": suite_fingerprint(raws),
        "source": source,
        "total": len(cases),
        "intents": dict(intent_counts),
        "required_layers": dict(required_counts),
        "provided_layers": dict(provided_counts),
        "three_layer_required": sum(case["three_layer_required"] for case in cases),
        "three_layer_ready": sum(case["three_layer_required"] and not case["missing_layers"] for case in cases),
        "executable": sum(case["executable"] for case in cases),
        "blocked": sum(bool(case["blocked"]) for case in cases),
        "coverage_gaps": sum(bool(case["missing_layers"]) for case in cases),
        "cases": cases,
    }


def write_suite_plan(plan: dict[str, Any], output_dir: str | Path) -> tuple[Path, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "suite_plan.json"
    md_path = output / "suite_plan.md"
    json_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# 测试套件规划与覆盖报告", "",
        f"- 套件指纹: `{plan['suite_id']}`", f"- 来源: `{plan.get('source', '')}`",
        f"- 用例总数: {plan['total']}", f"- 测试意图: {plan['intents']}",
        f"- 要求层: {plan['required_layers']}", f"- 已具备层: {plan['provided_layers']}",
        f"- 要求 UI+API+DB: {plan['three_layer_required']}",
        f"- 已具备 UI+API+DB: {plan['three_layer_ready']}",
        f"- 可直接执行: {plan['executable']}", f"- 业务口径阻塞: {plan['blocked']}",
        f"- 存在覆盖缺口: {plan['coverage_gaps']}", "",
        "|用例|标题|意图|要求层|已具备|缺口|状态|", "|---|---|---|---|---|---|---|",
    ]
    for case in plan["cases"]:
        status = "BLOCKED" if case["blocked"] else "READY" if case["executable"] else "DRAFT"
        lines.append(
            f"|{case['case_id']}|{case['title']}|{','.join(case['intents'])}|"
            f"{','.join(case['required_layers'])}|{','.join(case['provided_layers'])}|"
            f"{','.join(case['missing_layers']) or '—'}|{status}|"
        )
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def render_plan_html(plan: dict[str, Any]) -> str:
    rows = []
    for case in plan["cases"]:
        rows.append("<tr>" + "".join(f"<td>{html.escape(str(value))}</td>" for value in (
            case["case_id"], case["title"], ", ".join(case["intents"]),
            ", ".join(case["required_layers"]), ", ".join(case["provided_layers"]),
            ", ".join(case["missing_layers"]) or "—",
        )) + "</tr>")
    return "<table><tr><th>用例</th><th>标题</th><th>意图</th><th>要求层</th><th>已具备</th><th>缺口</th></tr>" + "".join(rows) + "</table>"

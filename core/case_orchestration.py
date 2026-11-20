"""Use-case-first planning and coverage accounting for UI Agent runs."""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from typing import Any

from core.agent_test_intake import AgentTestRequest, build_agent_plan
from core.case_source import RawCase
from core.suite_plan import classify_case


@dataclass
class CasePlan:
    case_id: str
    title: str
    source_row: int
    priority: str
    required_layers: list[str]
    instruction: str
    plan: dict[str, Any]
    source_refs: list[str]
    role: str = ""
    test_data: str = ""
    risk: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _instruction(case: RawCase) -> str:
    steps = case.steps_text.strip()
    expected = case.expected_text.strip()
    if expected:
        observable = expected
        if re.search(r"显示|展示|可见|出现|存在", expected) and not re.search(r"[“‘\"《【]", expected):
            value = re.sub(r"(?:应当|应该|成功|正确)?(?:显示|展示|可见|出现|存在).*$", "", expected).strip(" ：:，,")
            if value:
                observable = f"“{value}”显示"
        return f"{steps}；确认{observable}" if steps else f"确认{observable}"
    return steps or case.name


def _case_id(case: RawCase) -> str:
    match = re.match(r"^\s*([A-Za-z]+\d+)(?:\s*[-—_:：]|\s+|$)", case.name or "")
    return match.group(1) if match else (case.case_id or "case-" + hashlib.sha256(case.name.encode()).hexdigest()[:8])


def build_case_plans(cases: list[RawCase], url: str, source_manifest: dict[str, Any] | None = None) -> list[CasePlan]:
    refs = [str(item.get("path")) for item in (source_manifest or {}).get("sources", [])
            if item.get("status") == "INDEXED"]
    plans: list[CasePlan] = []
    for case in cases:
        instruction = _instruction(case)
        request = AgentTestRequest(url=url, instruction=instruction)
        plan = build_agent_plan(request).to_dict()
        classified = classify_case(case)
        case_id = _case_id(case)
        plans.append(CasePlan(case_id=case_id, title=case.name, source_row=case.row,
                              priority=case.level or "P2",
                              required_layers=list(classified.get("required_layers") or ["ui"]),
                              instruction=instruction, plan=plan, source_refs=refs,
                              role=case.role, test_data=case.test_data, risk=case.risk))
    return plans


def enrich_from_sources(plans: list[CasePlan], source_manifest: dict[str, Any] | None) -> dict[str, Any]:
    """Find likely missing coverage using evidence signals, without inventing cases."""
    case_text = "\n".join(f"{item.title}\n{item.instruction}" for item in plans).lower()
    signals = sorted({signal for source in (source_manifest or {}).get("sources", [])
                      for signal in source.get("signals", [])})
    expectations = {
        "authorization": ("权限", "角色", "越权", "permission", "role"),
        "state_machine": ("状态", "审批", "流转", "state", "status"),
        "validation": ("必填", "校验", "长度", "边界", "required", "validation"),
        "database": ("数据库", "落库", "数据一致", "sql", "table"),
        "api_contract": ("接口", "响应", "请求", "api", "http"),
        "async": ("异步", "消息", "队列", "event", "mq"),
    }
    gaps = []
    for signal in signals:
        terms = expectations.get(signal, ())
        if terms and not any(term in case_text for term in terms):
            gaps.append({"signal": signal, "status": "POTENTIAL_GAP",
                         "reason": "supporting material contains this risk, but no supplied case mentions it"})
    return {"signals": signals, "potential_case_gaps": gaps}


def coverage_report(plans: list[CasePlan], results: list[dict[str, Any]] | None = None,
                    source_manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    result_map = {str(item.get("case_id")): item for item in (results or [])}
    rows = []
    for item in plans:
        result = result_map.get(item.case_id, {})
        execution = result.get("execution") or {}
        rows.append({
            "case_id": item.case_id, "title": item.title, "priority": item.priority,
            "required_layers": item.required_layers,
            "role": item.role, "test_data": item.test_data, "risk": item.risk,
            "ui_actions": len(item.plan.get("actions") or []),
            "ui_oracles": len(item.plan.get("oracles") or []),
            "unresolved_expectations": item.plan.get("unresolved_expectations") or [],
            "status": result.get("status", "PLANNED"),
            "evidence": execution.get("evidence") or [],
            "source_refs": item.source_refs,
        })
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    return {"schema_version": 1, "case_count": len(rows), "status_counts": counts,
            "rows": rows, "not_covered": [row["case_id"] for row in rows if row["status"] == "PLANNED"],
            "evidence_analysis": enrich_from_sources(plans, source_manifest)}

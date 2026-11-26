"""Built-in P0-P2 capabilities used by the natural-language UI agent.

The functions in this module are deliberately evidence-producing and safe by
default.  They inspect the browser or workspace and never invent a PASS when
the corresponding external connector is absent.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any


def semantic_map(observation: dict[str, Any]) -> dict[str, Any]:
    """Normalize an observation into a compact, reusable page map."""
    controls = []
    for item in observation.get("controls") or []:
        name = str(item.get("text") or item.get("label") or item.get("name") or "").strip()
        if not name:
            continue
        controls.append({
            "name": name,
            "role": str(item.get("role") or item.get("tag") or ""),
            "href": str(item.get("href") or ""),
            "disabled": bool(item.get("disabled")),
            "readonly": bool(item.get("readonly")),
        })
    return {
        "url": observation.get("url", ""),
        "title": observation.get("title", ""),
        "headings": list(observation.get("headings") or []),
        "navigation": list(observation.get("navigation") or []),
        "breadcrumbs": list(observation.get("breadcrumbs") or []),
        "controls": controls,
        "fields": list(observation.get("fields") or []),
        "rows": list(observation.get("rows") or []),
        "tables": int(observation.get("tables") or 0),
        "dialogs": int(observation.get("dialogs") or 0),
    }


def page_map_fingerprint(page_map: dict[str, Any]) -> str:
    payload = json.dumps(page_map, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def accessibility_audit(page) -> dict[str, Any]:
    """Run a dependency-free, high-signal accessibility smoke audit."""
    script = r"""
    () => {
      const visible = e => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
      const named = e => (e.getAttribute('aria-label') || e.innerText || e.value ||
        e.getAttribute('title') || e.getAttribute('alt') || '').trim();
      const issues = [];
      document.querySelectorAll('button,a,[role="button"]').forEach(e => {
        if (visible(e) && !named(e)) issues.push({kind:'unnamed_control', tag:e.tagName.toLowerCase()});
      });
      document.querySelectorAll('input:not([type="hidden"]),textarea,select').forEach(e => {
        if (!visible(e) || e.disabled) return;
        const id = e.getAttribute('id');
        const label = (id && document.querySelector(`label[for="${CSS.escape(id)}"]`)) || e.closest('label');
        if (!label && !e.getAttribute('aria-label') && !e.getAttribute('placeholder'))
          issues.push({kind:'unlabeled_field', tag:e.tagName.toLowerCase(), name:e.name || e.id || ''});
      });
      document.querySelectorAll('img').forEach(e => {
        if (visible(e) && !e.getAttribute('alt')) issues.push({kind:'image_without_alt'});
      });
      const headings = Array.from(document.querySelectorAll('h1,h2,h3,h4,h5,h6')).filter(visible)
        .map(e => Number(e.tagName.substring(1)));
      for (let i=1; i<headings.length; i++)
        if (headings[i] - headings[i-1] > 1) issues.push({kind:'heading_level_skip', from:headings[i-1], to:headings[i]});
      return {issues, counts:{controls:document.querySelectorAll('button,a,[role="button"]').length,
        fields:document.querySelectorAll('input:not([type="hidden"]),textarea,select').length,
        images:document.querySelectorAll('img').length, headings:headings.length}};
    }
    """
    try:
        result = page.evaluate(script) or {"issues": [], "counts": {}}
        issues = list(result.get("issues") or [])
        return {"status": "PASSED" if not issues else "FINDINGS", "issue_count": len(issues), **result}
    except Exception as exc:
        return {"status": "INCONCLUSIVE", "issue_count": 0, "issues": [], "error": str(exc)[:300]}


def browser_quality(page, *, console_errors: list[dict[str, Any]] | None = None,
                    page_errors: list[dict[str, Any]] | None = None,
                    failed_requests: list[dict[str, Any]] | None = None,
                    thresholds: dict[str, float] | None = None) -> dict[str, Any]:
    """Collect frontend errors and navigation timing without judging business success."""
    try:
        timing = page.evaluate("""() => {
          const t = performance.getEntriesByType('navigation')[0];
          return t ? {dom_content_loaded: t.domContentLoadedEventEnd,
            load: t.loadEventEnd, response: t.responseEnd - t.requestStart} : {};
        }""") or {}
    except Exception:
        timing = {}
    console_errors = list(console_errors or [])
    page_errors = list(page_errors or [])
    failed_requests = list(failed_requests or [])
    thresholds = thresholds or {}
    threshold_failures = []
    for key, limit in thresholds.items():
        actual = timing.get(key)
        if actual is not None and float(actual) > float(limit):
            threshold_failures.append({"metric": key, "actual": actual, "limit": limit})
    return {
        "status": "FINDINGS" if console_errors or page_errors or failed_requests or threshold_failures else "PASSED",
        "console_errors": console_errors,
        "page_errors": page_errors,
        "failed_requests": failed_requests,
        "timing_ms": timing,
        "thresholds": thresholds,
        "threshold_failures": threshold_failures,
    }


def summarize_api_payload(payload: Any, *, max_items: int = 40) -> dict[str, Any]:
    """Keep JSON shape/scalars while avoiding credentials and large response bodies."""
    secret = re.compile(r"password|token|secret|cookie|authorization|identity", re.I)

    def clean(value: Any, key: str = "") -> Any:
        if secret.search(key):
            return "[redacted]"
        if isinstance(value, dict):
            return {str(k): clean(v, str(k)) for k, v in list(value.items())[:max_items]}
        if isinstance(value, list):
            return [clean(v, key) for v in value[:max_items]]
        if isinstance(value, (str, int, float, bool)) or value is None:
            text = str(value)
            return text[:500] if isinstance(value, str) else value
        return str(value)[:500]

    return clean(payload)


def extract_scalar(payload: Any, path: str) -> Any:
    current = payload
    for part in str(path).split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return None
    return current


def write_json(path: str | Path, value: Any) -> str:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return str(target)


def connector_readiness(workspace: str | Path) -> dict[str, Any]:
    """Report whether optional API/DB/event evidence sources are configured."""
    root = Path(workspace).resolve()
    config = root / "config"
    db_path = config / "db.yaml"
    eventmap = root / "knowledge_base" / "eventmap"
    return {
        "api": {"status": "AVAILABLE", "message": "browser network capture is built in"},
        "db": {"status": "AVAILABLE" if db_path.is_file() else "NEEDS_CONFIG",
               "message": "workspace/config/db.yaml" if db_path.is_file() else "add a read-only DB connector when DB proof is required"},
        "event": {"status": "AVAILABLE" if eventmap.is_dir() else "NEEDS_CONFIG",
                  "message": "workspace eventmap/connector" if eventmap.is_dir() else "add an event source when MQ/event proof is required"},
    }


def history_summary(workspace: str | Path, *, limit: int = 20) -> dict[str, Any]:
    root = Path(workspace).resolve() / "reports" / "agent-tests"
    rows = []
    if root.is_dir():
        for path in sorted(root.glob("*/summary.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
            try:
                item = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            rows.append({"run_id": item.get("run_id"), "status": item.get("status"),
                         "instruction": (item.get("plan") or {}).get("source_instruction", ""),
                         "report_dir": item.get("report_dir", str(path.parent))})
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    return {"total": len(rows), "counts": counts, "runs": rows}


def generate_scenarios(instruction: str) -> list[dict[str, Any]]:
    """Suggest safe, read-only scenario variants from a broad request."""
    text = instruction.lower()
    scenarios = [{"id": "happy_path", "title": "主流程", "risk": "read_only"}]
    if any(term in text for term in ("查询", "搜索", "筛选", "订单", "列表")):
        scenarios.extend([
            {"id": "empty_query", "title": "空条件查询", "risk": "read_only"},
            {"id": "not_found", "title": "不存在的数据", "risk": "read_only"},
            {"id": "reset_filter", "title": "重置筛选条件", "risk": "read_only"},
        ])
    if any(term in text for term in ("权限", "角色", "审批", "只读")):
        scenarios.extend([
            {"id": "authorized_role", "title": "有权限角色", "risk": "read_only"},
            {"id": "unauthorized_role", "title": "无权限角色", "risk": "read_only"},
        ])
    if any(term in text for term in ("提交", "保存", "创建", "发布", "审批")):
        scenarios.append({"id": "mutation_review", "title": "写操作（需显式授权）", "risk": "authorized_write"})
    return scenarios


# 每个场景如何落成一条"可执行指令草稿"。只做 read_only 场景的确定性改写(把场景意图
# 拼到原指令上),写操作场景(authorized_write)一律不自动展开——需显式人审授权。
# 零业务:这里不认任何业务词,只认 generate_scenarios 产出的通用场景 id。
_SCENARIO_INSTRUCTION = {
    "happy_path": "{base}",
    "empty_query": "{base}；用空条件执行查询，确认列表区域正常渲染",
    "not_found": "{base}；用一个不存在的数据执行查询，确认出现空结果或无数据提示",
    "reset_filter": "{base}；执行查询后重置筛选条件，确认条件被清空",
    "authorized_role": "{base}（以有权限角色只读查看）",
    "unauthorized_role": "{base}（以无权限角色只读查看，确认受限提示）",
}


def scenario_execution_drafts(request: Any) -> list[dict[str, Any]]:
    """把场景建议接成"执行闭环草稿":逐条场景 → 可执行 plan 草稿(draft 态,**不自动跑**)。

    兑现审计建议 #3(场景建议→执行闭环)的框架骨架。闭环分两步、物理隔离:
      ① 本函数只**生成草稿**:对每个 read_only 场景,把场景意图确定性改写成一条执行指令,
         复用 build_agent_plan 产出真实可执行的动作/断言计划,打上 draft 戳。
      ② 真正执行由 runner 显式驱动(本函数绝不触发浏览器、绝不改判定)——与"不自动晋级/
         read-only 优先"铁律一致。写操作场景(authorized_write)只列为 needs_authorization,
         不展开成可执行草稿,必须人工显式授权后另行处理。

    离线可验证:接线正确(场景→草稿一一对应、动作非空、写场景不展开),无需真实后端;
    "场景在陌生系统能不能真跑通"仍回到断言可信性(第一档)与真实运行(第三档),不在此冒充。
    """
    from core.agent_test_intake import AgentTestRequest, build_agent_plan

    base_instruction = str(getattr(request, "instruction", "") or "")
    url = str(getattr(request, "url", "") or "")
    role = str(getattr(request, "role", "default") or "default")
    drafts: list[dict[str, Any]] = []
    for scenario in generate_scenarios(base_instruction):
        sid = scenario.get("id")
        if scenario.get("risk") == "authorized_write":
            drafts.append({"scenario": sid, "title": scenario.get("title"),
                           "state": "needs_authorization", "plan": None,
                           "reason": "写操作场景需显式人审授权,不自动展开成可执行草稿"})
            continue
        template = _SCENARIO_INSTRUCTION.get(sid, "{base}")
        instruction = template.format(base=base_instruction)
        try:
            plan = build_agent_plan(AgentTestRequest(url=url, instruction=instruction, role=role))
            draft_plan = plan.to_dict()
        except Exception as exc:  # noqa: BLE001  单条场景建模失败不连累其余
            drafts.append({"scenario": sid, "title": scenario.get("title"),
                           "state": "draft_failed", "plan": None, "reason": str(exc)[:200]})
            continue
        drafts.append({"scenario": sid, "title": scenario.get("title"),
                       "instruction": instruction, "state": "draft",
                       "actions": draft_plan.get("actions") or [],
                       "oracles": draft_plan.get("oracles") or [],
                       "auto_executed": False})
    return drafts

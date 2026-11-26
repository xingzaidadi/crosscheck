"""Natural-language intake for autonomous, safety-bounded UI tests."""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from urllib.parse import urlparse

from core.case_source import RawCase
from core.ui_test_intake import build_ui_intent


ASSERTION_MARKERS = ("确认", "验证", "检查", "断言", "应当", "应该", "确保", "必须", "assert", "verify", "expect")


@dataclass
class AgentTestRequest:
    url: str
    instruction: str
    role: str = "default"
    risk_policy: str = "read_only"
    allow_write: bool = False
    write_scope: str = ""
    persist_regression: bool = False


@dataclass
class AgentTestPlan:
    plan_id: str
    title: str
    url: str
    role: str
    risk_policy: str
    actions: list[dict] = field(default_factory=list)
    oracles: list[dict] = field(default_factory=list)
    unresolved_expectations: list[str] = field(default_factory=list)
    write_risk: bool = False
    source_instruction: str = ""
    clarifications: list[dict] = field(default_factory=list)
    requested_layers: list[str] = field(default_factory=lambda: ["ui"])
    scenario_mode: str = "single"
    role_matrix: list[str] = field(default_factory=list)
    data_strategy: dict = field(default_factory=dict)
    quality_thresholds: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def validate_request(request: AgentTestRequest) -> list[dict[str, str]]:
    missing: list[dict[str, str]] = []
    parsed = urlparse(request.url or "")
    if parsed.scheme not in {"http", "https", "file"} or not (parsed.netloc or parsed.scheme == "file"):
        missing.append({"field": "url", "message": "请提供有效的 http/https/file 测试地址"})
    if not request.instruction.strip():
        missing.append({"field": "instruction", "message": "请用自然语言描述测试目标"})
    if request.risk_policy not in {"read_only", "authorized_write"}:
        missing.append({"field": "risk_policy", "message": "risk_policy 必须是 read_only 或 authorized_write"})
    if request.allow_write and not request.write_scope.strip():
        missing.append({"field": "write_scope", "message": "允许写操作时必须声明测试数据和清理范围"})
    return missing


def _split_instruction(instruction: str) -> tuple[str, str]:
    clauses = [part.strip() for part in re.split(r"[。；;\n]+", instruction) if part.strip()]
    action_clauses: list[str] = []
    expected_clauses: list[str] = []
    for clause in clauses:
        marker = next((item for item in ASSERTION_MARKERS if item.lower() in clause.lower()), "")
        if marker:
            expected_clauses.append(clause.split(marker, 1)[-1].strip("：:，, ") or clause)
        else:
            action_clauses.append(clause)
    if not action_clauses:
        action_clauses = clauses
    return "\n".join(action_clauses), "\n".join(expected_clauses)


def _deduplicate_oracles(oracles: list[dict]) -> list[dict]:
    kept: list[dict] = []
    for oracle in sorted(oracles, key=lambda item: len(str(item.get("value") or "")), reverse=True):
        value = str(oracle.get("value") or "")
        duplicate = any(
            oracle.get("kind") == existing.get("kind")
            and value and value in str(existing.get("value") or "")
            and oracle.get("expected") == existing.get("expected")
            for existing in kept
        )
        if not duplicate:
            kept.append(oracle)
    return list(reversed(kept))


def _instruction_actions(instruction: str) -> list[dict]:
    actions: list[dict] = []
    for match in re.finditer(
        r"(?:查询|搜索|查找|筛选)\s*(?:订单|记录|数据|编号|单号)?\s*[‘’“\"]?([A-Za-z0-9_-]{2,64})[’‘”\"]?",
        instruction,
        re.I,
    ):
        value = match.group(1).strip()
        if value and not any(item.get("action") == "search_value" and item.get("value") == value for item in actions):
            actions.append({"action": "search_value", "value": value, "purpose": "query"})
    for match in re.finditer(
        r"(?:在|向)?[‘’“”\"《》【】]?([^，。；;]{1,24}?)[’‘“”\"》】]?(?:输入框|输入框中|字段|条件)?(?:中)?"
        r"(?:输入|填写|搜索|查询)\s*[‘’“”\"《》【】]?([^，。；;]{1,40})",
        instruction,
    ):
        label, value = (item.strip(" ：:‘’“”\"《》【】") for item in match.groups())
        label = re.sub(r"输入框$", "", label).strip()
        value = re.sub(r"^(?:框|中|里)\s*", "", value).strip()
        value = re.sub(r"(?:并且|并|然后)(?:查询|搜索|筛选)$", "", value).strip()
        if label and value:
            actions.append({"action": "text", "label": label, "value": value, "purpose": "query"})
    for match in re.finditer(
        r"(?:点击|单击|打开|进入|切换到|选择|按下)\s*[‘’“”\"《》【】]?([^，。；;\s‘’“”\"《》【】]{1,40})",
        instruction,
    ):
        label = match.group(1).strip()
        if label and not any(item.get("action") == "click" and item.get("text") == label for item in actions):
            actions.append({"action": "click", "text": label})
    if re.search(r"(?:打开|查看|进入).*(?:第一条|首条|第一行).*(?:记录|订单|详情)|(?:第一条|首条|第一行).*(?:详情|记录)", instruction):
        actions.append({"action": "open_first_record"})
    if re.search(r"(?:下一页|第\s*2\s*页)", instruction):
        actions.append({"action": "go_to_page", "page": 2})
    if re.search(r"(?:重置|清空条件|清除筛选)", instruction):
        actions.append({"action": "click", "text": "重置"})
    if re.search(r"(?:筛选|过滤|搜索|查询).*(?:结果|列表|记录)?", instruction):
        if not any(item.get("action") == "click" and item.get("text") in {"搜索", "查询"} for item in actions):
            actions.append({"action": "click", "text": "查询"})
    if re.search(r"(?:下载|导出|download|export)", instruction, re.I):
        label = "导出" if "导出" in instruction else "下载" if "下载" in instruction else "Download"
        actions.append({"action": "download", "text": label})
    for match in re.finditer(r"(?:悬停|移到|hover)\s*[‘’“”\"《》【】]?([^，。；;\s’‘“”\"》】]{1,40})", instruction, re.I):
        actions.append({"action": "hover", "text": match.group(1).strip()})
    for match in re.finditer(r"(?:勾选|选中|check)\s*[‘’“”\"《》【】]?([^，。；;\s’‘“”\"》】]{1,40})", instruction, re.I):
        actions.append({"action": "check", "label": match.group(1).strip()})
    for match in re.finditer(r"(?:取消勾选|取消选中|uncheck)\s*[‘’“”\"《》【】]?([^，。；;\s’‘“”\"》】]{1,40})", instruction, re.I):
        actions.append({"action": "uncheck", "label": match.group(1).strip()})
    return actions


def _normalize_agent_actions(actions: list[dict], instruction: str) -> list[dict]:
    """Correct ambiguous prose actions before the observation planner sees them.

    ``打开订单中心`` is navigation; ``打开第一条订单`` is record access.  The
    legacy prose intake intentionally supports both, but its conservative
    record heuristic can emit ``open_first_record`` for a navigation label.
    The agent path has the full instruction and can make that distinction
    without requiring selectors or a case file.
    """
    text = str(instruction or "")
    asks_first = bool(re.search(r"(?:第一条|首条|第一行|第一个).*(?:记录|订单|数据|详情)|打开.*第一条", text))
    explicit_detail = bool(re.search(
        r"(?:打开|进入|查看|点击)\s*(?:(?:订单|记录|数据)\s*)?(?:详情|明细)", text,
    ))
    asks_record = asks_first or explicit_detail
    # 纯导航动词(打开/进入/切换到/跳转)后接的页面名视为"到达目标",改走 reach:
    # reach 的 action_visible 兼容语义命中(控件分≥70)且自带网关+退伍逻辑,比 click
    # 更能容忍"用例措辞≠控件名"(如用例'客户资料'、控件'会员档案')而不误判 BLOCKED。
    # 排除详情/记录类(由上面 record 逻辑处理)与显式"点击/单击/按下"的控件交互。
    nav_targets = {
        match.group(1).strip()
        for match in re.finditer(
            r"(?:打开|进入|切换到|跳转(?:到|至)?)\s*[‘’“”\"《》【】]?"
            r"([^，。；;\s‘’“”\"《》【】]{2,40})",
            text,
        )
        if not any(term in match.group(1) for term in ("详情", "明细", "第一条", "首条", "第一行"))
    }
    normalized: list[dict] = []
    for action in actions:
        if action.get("action") == "click" and str(action.get("text") or "") in nav_targets:
            goal = {"action": "reach", "target": str(action.get("text") or "")}
            if goal not in normalized:
                normalized.append(goal)
            continue

        if action.get("action") == "open_first_record" and explicit_detail and not asks_first:
            normalized.append({"action": "click", "text": "详情"})
            continue
        if action.get("action") == "open_first_record" and not (asks_first or asks_record):
            label = str(action.get("column") or "").strip()
            if label:
                replacement = {"action": "click", "text": label}
                if replacement not in normalized:
                    normalized.append(replacement)
            continue
        if action.get("action") == "click" and str(action.get("text") or "") == "详情" \
                and not explicit_detail:
            continue
        if asks_first and action.get("action") == "click" \
                and any(term in str(action.get("text") or "") for term in ("第一条", "首条", "第一行")):
            continue
        if action not in normalized:
            normalized.append(action)
    if asks_record and not any(item.get("action") == "open_first_record" for item in normalized):
        normalized.append({"action": "open_first_record"})
    return normalized


def _ensure_detail_navigation(actions: list[dict], instruction: str) -> list[dict]:
    """Make detail-page expectations executable instead of satisfied by a list button."""
    if not re.search(r"详情页|详情页面|进入详情|打开详情|查看详情", instruction):
        return actions
    has_detail_action = any(
        item.get("action") == "click" and str(item.get("text") or "") in {"详情", "查看详情", "明细"}
        for item in actions
    ) or any(item.get("action") == "open_first_record" for item in actions)
    if has_detail_action:
        return actions
    return [*actions, {"action": "click", "text": "详情"}]


def _normalize_execution_order(actions: list[dict]) -> list[dict]:
    """Compile prose actions into a safe user-visible order.

    Query values must be entered before the query button is clicked; detail
    navigation must happen after the query/record step.  This is a plan
    compiler concern, not a selector concern, so it remains reusable across
    applications.
    """
    unique: list[dict] = []
    for action in actions:
        if action.get("action") == "prepare_filter":
            continue
        if action not in unique:
            unique.append(action)
    query_inputs = [item for item in unique if item.get("action") in {"search_value", "text", "number"}
                    and item.get("purpose") == "query"]
    query_clicks = [item for item in unique if item.get("action") == "click"
                    and str(item.get("text") or "") in {"查询", "搜索", "筛选"}]
    detail_actions = [item for item in unique if item.get("action") == "click"
                      and str(item.get("text") or "") in {"详情", "查看详情", "明细"}]
    record_actions = [item for item in unique if item.get("action") in {"open_first_record", "select_first_row"}]
    consumed = set(map(id, query_inputs + query_clicks + detail_actions + record_actions))
    remainder = [item for item in unique if id(item) not in consumed]
    ordered = query_inputs + [item for item in remainder if item.get("action") not in {"click", "reach"}]
    ordered += query_clicks
    ordered += [item for item in remainder if item.get("action") in {"click", "reach"}]
    ordered += record_actions + detail_actions
    return ordered


def _natural_language_oracles(instruction: str) -> list[dict]:
    oracles: list[dict] = []
    for match in re.finditer(
        r"(?:字段|状态|结果|文本)?\s*(?:并且?|然后)?\s*(?:确认|验证|检查)?\s*[‘’“\"]?([\u4e00-\u9fffA-Za-z_][\u4e00-\u9fffA-Za-z0-9_-]{1,30})[’‘”\"]?\s*(?:为|是(?!否)|等于|显示为|应为)\s*[‘’“\"]?([^，。；;’‘”\"]{1,60})",
        instruction,
    ):
        field, value = match.groups()
        field = field.strip()
        value = value.strip()
        span = match.group(0)
        # 铁律『不假通过』:"是否X""X是否正常"是存活性问句,不是字段断言,抽成
        # field_text_equals 会凭空造出 `字段=否正常` 之类伪断言并在运行时误判。旧实现
        # 靠黑名单(确认/页面/订单/详情)根本挡不住——根因是正则把"是否"里的"是"当等号。
        # 双保险:① 操作符 `是(?!否)` 不吃"是否"的是;② 兜底:匹配跨度含"是否"、字段
        # 以"是否"收尾、或值以"否"开头(被截断残片)一律丢弃。等号两侧必须都是实词才成断言。
        if "是否" in span or field.endswith("是否") or value.startswith("否"):
            continue
        if field in {"确认", "页面", "订单", "详情"} or not field or not value:
            continue
        oracles.append({"kind": "field_text_equals", "value": field,
                        "expected": value, "source": span, "fields": []})
    return oracles


def _instruction_goals(instruction: str) -> list[dict]:
    goals: list[dict] = []
    patterns = (
        r"(?:验证|检查|测试|确认)(?:一下|下)?[‘’“\"《》【】]?([^，。；;]{2,40}?)(?:页面|模块|功能|流程)?(?:是否)?(?:正常|可用|正确|成功)(?:[’‘”\"》】]|$|[，。；;])",
        r"(?:帮我|请)?(?:验证|检查|测试)[‘’“\"《》【】]?([^，。；;]{2,40}?)(?:页面|模块|功能|流程)?(?:是否)?(?:正常|可用|正确|成功)?(?:[’‘”\"》】]|$|[，。；;])",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, instruction, re.I):
            target = match.group(1).strip(" ：:，,‘’“”\"《》【】")
            target = re.sub(r"(?:是否|是不是|能否|可以)?(?:正常|可用|正确|成功)$", "", target).strip()
            if not target or "只读" in target or "不可编辑" in target \
                    or any(marker in target for marker in ASSERTION_MARKERS):
                continue
            goal = {"action": "reach", "target": target}
            if goal not in goals:
                goals.append(goal)
    return goals


def _requested_layers(instruction: str) -> list[str]:
    """Identify cross-layer expectations without pretending they were verified."""
    lowered = instruction.lower()
    layers = ["ui"]
    if any(term in lowered for term in ("接口", "api", "请求", "响应", "网络")):
        layers.append("api")
    if any(term in lowered for term in ("数据库", "db", "落库", "数据表", "持久化")):
        layers.append("db")
    if any(term in lowered for term in ("消息", "mq", "事件", "异步")):
        layers.append("event")
    return list(dict.fromkeys(layers))


def _role_matrix(instruction: str, default_role: str) -> list[str]:
    roles = [default_role or "default"]
    matches = re.findall(r"(?:角色|用户|账号|身份)\s*[：:为是]?\s*([\u4e00-\u9fffA-Za-z0-9_-]{2,24})", instruction)
    roles.extend(matches)
    if any(term in instruction for term in ("权限", "无权限", "越权", "审批")):
        roles.extend(["authorized", "unauthorized"])
    return list(dict.fromkeys(roles))


def _data_strategy(instruction: str, request: AgentTestRequest) -> dict:
    write_terms = ("创建", "新增", "保存", "提交", "审批", "发布", "删除", "上传")
    mutating = any(term in instruction for term in write_terms)
    return {
        "mode": "marker_and_cleanup" if mutating else "read_only_existing_data",
        "marker_required": mutating,
        "cleanup_required": mutating,
        "authorized": bool(request.allow_write and request.write_scope.strip()),
        "write_scope_provided": bool(request.write_scope.strip()),
    }


def _quality_thresholds(instruction: str) -> dict[str, float]:
    thresholds: dict[str, float] = {}
    patterns = {
        "load": r"(?:加载|首屏|页面).{0,12}?(?:不超过|小于|低于|<)\s*(\d+(?:\.\d+)?)\s*(?:ms|毫秒|秒)?",
        "dom_content_loaded": r"DOMContentLoaded.{0,12}?(?:不超过|小于|低于|<)\s*(\d+(?:\.\d+)?)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, instruction, re.I)
        if match:
            value = float(match.group(1))
            if "秒" in match.group(0) and key == "load":
                value *= 1000
            thresholds[key] = value
    return thresholds


def _layer_oracles(instruction: str) -> list[dict]:
    """Extract safe, evidence-bound API expectations from plain language."""
    lowered = instruction.lower()
    output: list[dict] = []
    db_match = re.search(
        r"(?:表|数据表)\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?:的|字段)?\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?:为|是|等于|=)\s*[‘’“\"]?([^，。；;‘’”\"]+)",
        instruction,
        re.I,
    )
    if db_match and any(term in lowered for term in ("数据库", "落库", "数据表", "db")):
        output.append({
            "kind": "db_scalar",
            "table": db_match.group(1),
            "column": db_match.group(2),
            "value": db_match.group(3).strip(),
            "expected": True,
            "source": db_match.group(0),
            "fields": [],
        })
    if not any(term in lowered for term in ("接口", "api", "请求", "响应", "网络")):
        return output
    status_match = re.search(r"(?:状态码|status|响应码|返回码)\s*(?:为|是|等于|=)?\s*(\d{3})", instruction, re.I)
    field_match = re.search(
        r"(?:接口|api).{0,30}?(?:字段|返回|响应)\s*[‘’“\"]?([A-Za-z_][A-Za-z0-9_.]*)[’‘”\"]?\s*(?:为|是|等于|=)\s*[‘’“\"]?([^，。；;’‘”\"]+)",
        instruction,
        re.I,
    )
    if field_match:
        output.append({
            "kind": "api_field",
            "path": field_match.group(1),
            "value": field_match.group(2).strip(),
            "expected": True,
            "source": field_match.group(0),
            "fields": [],
        })
    if not status_match:
        output.append({
            "kind": "api_observed",
            "value": "response",
            "expected": True,
            "source": "API layer requested without a concrete status oracle",
            "fields": [],
        })
        return output
    output.append({
        "kind": "api_status",
        "value": status_match.group(1),
        "expected": True,
        "source": status_match.group(0),
        "fields": [],
    })
    return output


def _clarifications(instruction: str, *, oracles: list[dict], actions: list[dict]) -> list[dict]:
    """Return questions only when the request cannot produce objective evidence."""
    questions: list[dict] = []
    if not actions or all(item.get("action") == "observe" for item in actions):
        if not oracles:
            questions.append({
                "id": "target_or_expected_result",
                "question": "请说明要测试的页面/功能，以及可观察的成功标准。",
                "examples": ["打开订单中心并确认列表可见", "查询订单1001并确认状态为待处理"],
            })
    return questions


def build_agent_plan(request: AgentTestRequest) -> AgentTestPlan:
    errors = validate_request(request)
    if errors:
        raise ValueError("; ".join(item["message"] for item in errors))
    steps, expected = _split_instruction(request.instruction)
    raw_case = RawCase(
        name="NL-UI-" + hashlib.sha256(request.instruction.encode("utf-8")).hexdigest()[:8],
        steps_text=steps,
        expected_text=expected,
    )
    intent = build_ui_intent(raw_case, request.url)
    inferred = _instruction_actions(request.instruction)
    if not inferred:
        inferred = _instruction_goals(steps)
    inferred = _normalize_agent_actions(inferred, request.instruction)
    intent.actions = _normalize_agent_actions(intent.actions, request.instruction)
    # Prefer the agent-specific plan whenever it has a concrete query/value;
    # the legacy UI intake otherwise adds a generic prepare_filter/click pair
    # before the value can be entered.
    if any(item.get("action") in {"search_value", "text", "number"} and item.get("purpose") == "query"
           for item in inferred):
        intent.actions = [item for item in intent.actions if item.get("action") not in {"prepare_filter"}]
    for action in inferred:
        if action not in intent.actions:
            intent.actions.append(action)
    intent.actions = _ensure_detail_navigation(intent.actions, request.instruction)
    intent.actions = _normalize_execution_order(intent.actions)
    if not intent.actions:
        intent.actions.append({"action": "observe", "target": "current_page"})
    goals = [item for item in intent.actions if item.get("action") == "reach"]
    existing_oracle_kinds = {
        item.kind if hasattr(item, "kind") else item.get("kind") for item in intent.oracles
    }
    if goals and not existing_oracle_kinds.intersection({"page_health", "visibility"}):
        target = str(goals[0].get("target") or "").strip()
        if target:
            intent.oracles.append({
                "kind": "visibility", "value": target, "expected": True,
                "source": "natural-language target should be observable", "fields": [],
            })
    if any(word in request.instruction for word in ("正常", "可用", "健康", "成功打开", "能打开")):
        intent.oracles.append({
            "kind": "page_health", "value": "page", "expected": True,
            "source": "natural-language health expectation", "fields": [],
        })
    if re.search(r"详情页|详情页面|进入详情|打开详情|查看详情", request.instruction):
        intent.oracles.append({
            "kind": "detail_page", "value": "详情", "expected": True,
            "source": "natural-language detail-page expectation", "fields": [],
        })
    intent.oracles.extend(_layer_oracles(request.instruction))
    intent.oracles.extend(_natural_language_oracles(request.instruction))
    requested_layers = _requested_layers(request.instruction)
    clarifications = _clarifications(request.instruction, oracles=intent.oracles, actions=intent.actions)
    data_strategy = _data_strategy(request.instruction, request)
    if data_strategy["cleanup_required"] and not data_strategy["authorized"]:
        clarifications.append({
            "id": "write_scope",
            "question": "该测试包含写操作。请确认测试数据范围、允许动作和清理/补偿策略，或改为只读验证。",
            "examples": ["允许创建 AUTOTEST 订单并在完成后删除", "只验证页面，不执行提交"],
        })
    return AgentTestPlan(
        plan_id=raw_case.name,
        title=request.instruction[:80],
        url=intent.page_url,
        role=request.role,
        risk_policy=request.risk_policy,
        actions=list(intent.actions),
        oracles=_deduplicate_oracles([
            item.to_dict() if hasattr(item, "to_dict") else item for item in intent.oracles
        ]),
        unresolved_expectations=list(intent.unresolved_expectations),
        write_risk=bool(intent.write_risk),
        source_instruction=request.instruction,
        clarifications=clarifications,
        requested_layers=requested_layers,
        scenario_mode="matrix" if any(term in request.instruction for term in ("全部场景", "边界", "异常", "回归", "权限")) else "single",
        role_matrix=_role_matrix(request.instruction, request.role),
        data_strategy=data_strategy,
        quality_thresholds=_quality_thresholds(request.instruction),
    )

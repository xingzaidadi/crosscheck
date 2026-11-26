"""Turn prose UI cases into conservative browser execution intents."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import urljoin, urlparse

from core.exploration_actions import extract_safe_labels


_SEMANTICS_PATH = Path(__file__).resolve().parent.parent / "crosscheck_templates" / "ui_semantics.yaml"


def _semantic_config() -> dict:
    try:
        import yaml
        return yaml.safe_load(_SEMANTICS_PATH.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError, ImportError):
        return {}


_SEMANTICS = _semantic_config()
_WRITE_TERMS = tuple(_SEMANTICS.get("write_terms") or (
    "提交", "保存", "删除", "新增", "新建", "上传", "导入", "审批", "驳回", "关闭", "编辑", "创建", "发布", "作废", "撤回"
))
WRITE_ACTION = re.compile(r"(?:点击|选择|执行|调用|进行|填写|修改|确认|操作|批量)?\s*(?:" + "|".join(map(re.escape, _WRITE_TERMS)) + r")")
VISIBILITY_WORDS = ("显示", "可见", "存在", "出现", "展示", "show", "visible", "display")
ABSENCE_WORDS = ("不显示", "不可见", "不存在", "隐藏", "not visible", "hidden", "absent")
QUOTED = re.compile(r"[“‘\"《【]([^”’\"》】]{1,80})[”’\"》】]")
URL_PATH = re.compile(r"(?:https?://[^\s，。；]+|/[A-Za-z0-9_./?=&%-]+)")
CLICK_LABEL = re.compile(r"(?:点击|选择|打开|切换|查看|click|select|open|switch|view)\s*[“‘\"《【]?([^”’\"》】，。；\s]{1,40})", re.I)


@dataclass
class UiOracle:
    kind: str
    value: str
    expected: object = True
    source: str = ""
    fields: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class UiIntent:
    case_id: str
    title: str
    page_url: str
    source_steps: str = ""
    source_expected: str = ""
    source_preconditions: str = ""
    source_module: str = ""
    actions: list[dict] = field(default_factory=list)
    oracles: list[UiOracle] = field(default_factory=list)
    write_risk: bool = False
    unresolved_expectations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _lines(value: str) -> list[str]:
    return [re.sub(r"^\s*(?:\d+[.、)]|[-*])\s*", "", item).strip()
            for item in str(value or "").splitlines() if item.strip()]


def _cue_text(line: str) -> str:
    """去掉引号内目标字面后的"措辞文本",用于判定可见/缺失等语义线索。

    铁律『断言绑定目标字段』:缺失词(不存在/隐藏…)或可见词只应来自用户自己的措辞,
    而非目标文本内容。若引号里的字面恰好含"不存在"之类词(如确认出现文本"…不存在…"),
    不该把断言期望翻成 False——那会造成"目标缺失=预期缺失"的误通过。
    """
    return QUOTED.sub(" ", line or "")


def _labels(value: str) -> list[str]:
    labels = [item.strip() for item in QUOTED.findall(value or "") if item.strip()]
    labels.extend(extract_safe_labels(value))
    return list(dict.fromkeys(labels))


def _action_labels(value: str) -> list[str]:
    """Extract conservative UI labels from compound prose actions."""
    labels: list[str] = []
    for label in extract_safe_labels(value):
        labels.extend(re.split(r"[/、,，]", str(label)))
    for match in CLICK_LABEL.finditer(value):
        labels.extend(re.split(r"[/、,，]", match.group(1)))
    labels.extend(match.group(1).strip() for match in re.finditer(
        r"点击\s*(?:列表)?([^\s、，。；/]+)", value
    ))
    normalized = []
    for label in labels:
        item = label.strip().strip("“”‘’\"'《》【】")
        item = re.sub(r"(?:页签|模式页签)$", "", item)
        if item and len(item) <= 30 and item not in {"页面", "列表"}:
            normalized.append(item)
    return list(dict.fromkeys(normalized))


def _structured_actions(value: str) -> list[dict]:
    actions: list[dict] = []
    text = str(value or "")
    frame_match = re.search(r"(?:在|切换到)\s*(?:iframe|框架)\s*[“‘\"《【]?([^”’\"》】\s]{1,120})[”’\"》】]?", text, re.I)
    if frame_match:
        actions.append({"action": "frame_click", "frame": frame_match.group(1).strip(),
                        "role": "button", "name": "提交"})
    if re.search(r"新窗口|新标签页|打开新页", text):
        actions.append({"action": "wait_for", "selector": "body", "state": "visible"})
    record_match = re.search(r"(?:点击|进入|查看|打开)(?:列表中的|列表首条|首条|第一条)?\s*[“‘\"《【]?([^”’\"》】\s，。；]{2,40}?)(?:进入详情|查看详情|详情)?(?:$|[，。；\s])", text)
    if record_match and re.search(r"列表|首条|第一条|详情", text):
        column = record_match.group(1).strip()
        actions.append({"action": "open_first_record", "column": column})
    if re.search(r"筛选|过滤|查询", text):
        actions.append({"action": "prepare_filter", "preserve": True})
    if re.search(r"分页|翻页|第\s*\d+\s*页", text):
        page = re.search(r"第\s*(\d+)\s*页", text)
        actions.append({"action": "go_to_page", "page": int(page.group(1)) if page else 2})
    if re.search(r"勾选|选中", text):
        actions.append({"action": "select_first_row"})
    if re.search(r"状态页签|待处理/执行中/全部|整单/明细", text):
        known_tabs = [label for label in ("待处理", "执行中", "全部") if label in text]
        if "整单/明细" in text:
            known_tabs.extend(["整单查询", "明细查询"])
        actions.append({"action": "switch_tabs", "labels": list(dict.fromkeys(known_tabs))})
    elif "切换" in text and "页签" in text:
        actions.append({"action": "switch_tabs", "labels": []})
    for match in re.finditer(
        r"(?:填写|输入|填入|设置)\s*[“‘\"《【]?([^”’\"》】：:，,\s]{1,40})[”’\"》】]?\s*(?:为|成|:|：)\s*[“‘\"《【]?([^”’\"》】\n，,。；;]{1,80})",
        text,
    ):
        actions.append({"action": "text", "label": match.group(1).strip(),
                        "value": match.group(2).strip()})
    for match in re.finditer(
        r"(?:选择|选取)\s*[“‘\"《【]?([^”’\"》】：:，,\s]{1,40})[”’\"》】]?\s*(?:为|成|:|：)\s*[“‘\"《【]?([^”’\"》】\n，,。；;]{1,80})",
        text,
    ):
        actions.append({"action": "select", "label": match.group(1).strip(),
                        "value": match.group(2).strip()})
    for match in re.finditer(
        r"(?:日期|时间)字段?\s*[“‘\"《【]?([^”’\"》】：:，,\s]{1,40})[”’\"》】]?\s*(?:为|成|:|：)\s*[“‘\"《【]?([^”’\"》】\n，,。；;]{1,40})",
        text,
    ):
        actions.append({"action": "date", "label": match.group(1).strip(),
                        "value": match.group(2).strip()})
    for match in re.finditer(r"(?:按|键入|输入)\s*([A-Za-z]+(?:\+[A-Za-z]+)?)\s*(?:键|提交)?", text, re.I):
        key = match.group(1)
        if key.lower() in {"enter", "tab", "escape", "esc"} or "+" in key:
            actions.append({"action": "press", "key": "Escape" if key.lower() == "esc" else key.title()})
    for match in re.finditer(r"(?:悬停|移到|hover)\s*[“‘\"《【]?([^”’\"》】，。；\s]{1,40})", text, re.I):
        actions.append({"action": "hover", "text": match.group(1).strip()})
    for match in re.finditer(r"(?:勾选|选中|check)\s*[“‘\"《【]?([^”’\"》】，。；\s]{1,40})", text, re.I):
        actions.append({"action": "check", "label": match.group(1).strip()})
    for match in re.finditer(r"(?:取消勾选|取消选中|uncheck)\s*[“‘\"《【]?([^”’\"》】，。；\s]{1,40})", text, re.I):
        actions.append({"action": "uncheck", "label": match.group(1).strip()})
    return actions


def _page_url(base_url: str, text: str) -> str:
    match = URL_PATH.search(text or "")
    if not match:
        return base_url
    value = match.group(0)
    if value.startswith("http"):
        return value
    if "/api/" in value or value.startswith("/api"):
        return base_url
    return urljoin(base_url.rstrip("/") + "/", value.lstrip("/"))


def build_ui_intent(raw_case, base_url: str) -> UiIntent:
    steps = str(raw_case.steps_text or "")
    expected = str(raw_case.expected_text or "")
    combined = f"{raw_case.name}\n{raw_case.preconditions}\n{steps}\n{expected}"
    intent = UiIntent(
        case_id=str(raw_case.case_id),
        title=str(raw_case.name),
        page_url=_page_url(base_url, steps),
        source_steps=steps,
        source_expected=expected,
        source_preconditions=str(raw_case.preconditions or ""),
        source_module=str(raw_case.module or ""),
        write_risk=bool(WRITE_ACTION.search(steps)),
    )
    intent.actions.extend(_structured_actions(steps))
    for label in _action_labels(steps):
        if label in {"搜索", "查询"} and re.search(r"搜索框|查询框|输入框", steps):
            continue
        if any(token in label for token in ("与", "以及", "并且")):
            continue
        candidate = {"action": "click", "text": label}
        if not any(item == candidate for item in intent.actions):
            intent.actions.append(candidate)
    for line in _lines(expected):
        labels = _labels(line)
        url_match = URL_PATH.search(line) if any(word in line for word in ("跳转", "地址", "URL", "url")) else None
        if url_match:
            intent.oracles.append(UiOracle("url_contains", url_match.group(0), True, line))
            continue
        cue = _cue_text(line)
        if labels and any(word in cue for word in ABSENCE_WORDS):
            intent.oracles.extend(UiOracle("visibility", label, False, line) for label in labels)
            continue
        equals_match = re.search(r"[“‘\"《【]([^”’\"》】]{1,80})[”’\"》】]\s*(?:等于|为|是)\s*[“‘\"《【]([^”’\"》】]{1,120})[”’\"》】]", line)
        if equals_match:
            intent.oracles.append(UiOracle("field_value_equals", equals_match.group(1), equals_match.group(2), line))
            continue
        status_words = tuple(_SEMANTICS.get("status_terms") or ())
        if any(word in line for word in status_words) and any(word in cue for word in VISIBILITY_WORDS):
            intent.oracles.append(UiOracle("status_groups", "status", True, line,
                                           fields=list(_SEMANTICS.get("status_groups") or [])))
            continue
        if labels and any(word in cue for word in VISIBILITY_WORDS):
            intent.oracles.extend(UiOracle("visibility", label, True, line) for label in labels)
            continue
        if re.search(r"(?:模糊匹配|交集过滤|多选.*生效|筛选准确)", line):
            intent.oracles.append(UiOracle("filter_controls", "query", True, line,
                                           fields=list(_SEMANTICS.get("filter_fields") or [])))
            continue
        if re.search(r"只读|不可编辑|无编辑", line):
            intent.oracles.append(UiOracle("readonly", "page", True, line))
            continue
        if re.search(r"第\s*1\s*页|第一页|分页重置", line):
            intent.oracles.append(UiOracle("pagination_page", "1", True, line))
            continue
        if re.search(r"清空.*勾选|勾选.*清空|没有勾选", line):
            intent.oracles.append(UiOracle("selected_row_count", "0", True, line))
            continue
        if re.search(r"(?:每页|分页默认)\s*10|10\s*条/页", line):
            intent.oracles.append(UiOracle("page_size", "10", True, line))
            continue
        attr_match = re.search(r"[“‘\"《【]([^”’\"》】]{1,80})[”’\"》】].*(?:禁用|不可用|disabled)", line, re.I)
        if attr_match:
            intent.oracles.append(UiOracle("enabled", attr_match.group(1), False, line))
            continue
        regex_match = re.search(r"(?:匹配|符合正则|regex)\s*[：:]?\s*[“‘\"《【]?([^”’\"》】]{1,120})", line, re.I)
        if regex_match:
            intent.oracles.append(UiOracle("text_matches", regex_match.group(1), True, line))
            continue
        count_match = re.search(r"(?:共|数量为|条数为)\s*(\d+)\s*(?:条|个)?", line)
        if count_match:
            intent.oracles.append(UiOracle("count", count_match.group(1), True, line))
        contains_match = re.search(r"(?:包含|含有)\s*[“‘\"《【]?([^”’\"》】]{1,80})[”’\"》】]?", line)
        if contains_match:
            intent.oracles.append(UiOracle("text_contains", contains_match.group(1), True, line))
            continue
        if count_match:
            continue
        intent.unresolved_expectations.append(line)
    return intent


def validate_intake(*, cases: str, base_url: str, session: str = "") -> list[dict[str, str]]:
    missing = []
    if not cases:
        missing.append({"field": "cases", "message": "请提供 UI 用例文件"})
    parsed = urlparse(base_url or "")
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        missing.append({"field": "url", "message": "请提供有效的测试环境地址（http/https）"})
    if session and not session.strip():
        missing.append({"field": "session", "message": "登录态路径不能为空"})
    return missing

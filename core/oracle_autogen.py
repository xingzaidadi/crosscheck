"""
业务 Oracle 自动生成器(通用、零业务、纯函数、确定性)。

职责:从三类确定性证据产出"候选 Oracle"(core.oracle.py 格式),每条带置信度 + 证据 + 审计:
  - 用例预期文本 expected_text
  - 接口契约:抓包样本(response_json)
  - 库约束:db_intel.table_constraints 的 {col:{required,type,enum,...}}

红线(见 docs/ORACLE_AUTOGEN.md):
  - 只产 status=candidate,绝不置 verify_status / human_verified;
  - core 零业务:领域文本模式来自 workspace/config/oracle_patterns.yaml,core 只做"按规则抽取";
  - 无证据的 expected 判低置信并标注,不混入高分。

置信度为可解释加法分,每分可回溯(见 _score)。阈值只影响排序/提示,不影响人审闸。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# core.oracle.py 支持的算子(生成器只产其中之一,保证可被评估器直接消费)
_SUPPORTED_OPERATORS = {"equals", "not_equals", "contains", "exists", "matches", "gte", "lte", "in"}

# 置信度权重(与 docs/ORACLE_AUTOGEN.md §4 一致;可解释、可回溯)
_W_PATTERN = 0.4     # 预期文本命中结构化模式
_W_SUBJECT = 0.3     # subject 能在抓包样本里找到实际路径
_W_EXPECTED = 0.2    # expected 值可确定(文本/库约束)
_W_MAPPING = 0.1     # 已审映射支持该字段

HIGH_CONFIDENCE = 0.7
LOW_CONFIDENCE = 0.4


@dataclass
class OracleCandidate:
    id: str
    layer: str                     # ui | api | db
    subject: str                   # core.oracle.py 的点路径
    operator: str
    expected: Any
    confidence: float
    source: str                    # 人读的来源说明
    evidence_refs: list[str] = field(default_factory=list)
    status: str = "candidate"      # 永远 candidate,不自动过闸
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = {
            "id": self.id, "layer": self.layer, "subject": self.subject,
            "operator": self.operator, "expected": self.expected,
            "confidence": round(self.confidence, 3), "source": self.source,
            "evidence_refs": list(self.evidence_refs), "status": self.status,
        }
        if self.notes:
            data["notes"] = list(self.notes)
        return data


# ───────────────────────── 规则装载(零业务:全来自 workspace) ─────────────────────────

_DEFAULT_RULES: dict[str, Any] = {"patterns": []}


def load_rules(rules: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    规则结构(workspace/config/oracle_patterns.yaml):
      patterns:
        - match: "至少(\\d+)条|存在|显示"   # 预期文本正则
          layer: api                         # ui|api|db
          operator: gte                      # 复用 oracle.py 算子
          subject_hint: "data.total,data.records"  # 候选 subject(逗号分隔,按序找存在的)
          expected_from: "group1|literal:1|none"   # 取值来源
          expected: 1                        # expected_from=literal 时用
    core 不认任何领域词;规则空则不产正向候选(仅返回空)。
    """
    if rules is not None:
        return rules
    try:
        import yaml
        from core.workspace import config_dir
        path = config_dir() / "oracle_patterns.yaml"
        if path.exists():
            return yaml.safe_load(path.read_text(encoding="utf-8")) or _DEFAULT_RULES
    except Exception:  # noqa: BLE001
        pass
    return _DEFAULT_RULES


# ───────────────────────── 证据探测(确定性) ─────────────────────────

def _dig(obj: Any, dotted: str) -> Any:
    """按点路径取值(与 oracle.dig 同语义);取不到返回 _MISSING。"""
    cur = obj
    for part in str(dotted or "").replace("[", ".").replace("]", "").split("."):
        if not part:
            continue
        if isinstance(cur, dict):
            if part not in cur:
                return _MISSING
            cur = cur[part]
        elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        else:
            return _MISSING
    return cur


_MISSING = object()


def _subject_exists(subject: str, api_sample: dict[str, Any] | None) -> bool:
    if not api_sample:
        return False
    body = api_sample.get("response_json", api_sample)
    return _dig(body, subject) is not _MISSING


def _pick_subject(hint: str, api_sample: dict[str, Any] | None) -> tuple[str, bool]:
    """从 subject_hint(逗号分隔)里挑第一个在样本中存在的路径;都不存在取首个并标 found=False。"""
    candidates = [h.strip() for h in str(hint or "").split(",") if h.strip()]
    for candidate in candidates:
        if _subject_exists(candidate, api_sample):
            return candidate, True
    return (candidates[0] if candidates else ""), False


# ───────────────────────── 置信度打分(可解释) ─────────────────────────

def score(*, pattern_hit: bool, subject_found: bool, expected_known: bool,
          mapping_supported: bool) -> float:
    total = 0.0
    if pattern_hit:
        total += _W_PATTERN
    if subject_found:
        total += _W_SUBJECT
    if expected_known:
        total += _W_EXPECTED
    if mapping_supported:
        total += _W_MAPPING
    return round(min(total, 1.0), 3)


def _resolve_expected(pattern: dict[str, Any], text_match: re.Match | None) -> tuple[Any, bool]:
    """按 expected_from 规则取 expected 值,返回 (值, 是否可确定)。"""
    source = str(pattern.get("expected_from") or "none")
    if source.startswith("group") and text_match is not None:
        index = source[len("group"):]
        try:
            raw = text_match.group(int(index))
            return (int(raw) if str(raw).isdigit() else raw), True
        except (IndexError, ValueError):
            return None, False
    if source.startswith("literal:"):
        literal = source[len("literal:"):]
        return (int(literal) if literal.isdigit() else literal), True
    if source == "literal":
        return pattern.get("expected"), ("expected" in pattern)
    return None, False


# ───────────────────────── 主入口 ─────────────────────────

def generate(
    expected_text: str,
    *,
    api_sample: dict[str, Any] | None = None,
    db_constraints: dict[str, dict[str, Any]] | None = None,
    mapped_fields: set[str] | None = None,
    rules: dict[str, Any] | None = None,
    sample_ref: str = "",
) -> list[dict[str, Any]]:
    """
    从预期文本 + 接口样本 + 库约束产出候选 Oracle 列表(dict,core.oracle.py 可直接评估)。

    - expected_text: 用例预期(散文)
    - api_sample: 抓包样本(含 response_json)
    - db_constraints: {col:{required,type,enum,...}}(DB 侧 Oracle 证据;可选)
    - mapped_fields: 已审映射支持的字段名集合(提升置信;可选)
    - rules: 领域模式(默认从 workspace 装载)
    返回每条带 confidence/source/evidence_refs,status 恒为 candidate。
    """
    text = str(expected_text or "").strip()
    rules = load_rules(rules)
    mapped_fields = mapped_fields or set()
    candidates: list[OracleCandidate] = []
    index = 0

    for pattern in rules.get("patterns") or []:
        regex = pattern.get("match")
        if not regex:
            continue
        try:
            match = re.search(str(regex), text)
        except re.error:
            continue  # workspace 规则正则非法:跳过该条,不崩整体生成
        if not match:
            continue
        operator = str(pattern.get("operator") or "exists")
        if operator not in _SUPPORTED_OPERATORS:
            continue
        layer = str(pattern.get("layer") or "api")
        subject, subject_found = _pick_subject(pattern.get("subject_hint", ""), api_sample)
        expected, expected_known = _resolve_expected(pattern, match)
        mapping_supported = bool(subject and subject.split(".")[-1] in mapped_fields)

        confidence = score(pattern_hit=True, subject_found=subject_found,
                           expected_known=expected_known, mapping_supported=mapping_supported)
        notes: list[str] = []
        if not subject_found:
            notes.append("subject 未在抓包样本中找到,需人工确认路径")
        if not expected_known:
            notes.append("expected 无法从文本/库约束确定,需人工补")

        index += 1
        evidence_refs = []
        if subject_found and sample_ref:
            evidence_refs.append(f"{sample_ref}#{subject}")

        candidates.append(OracleCandidate(
            id=f"auto-{layer}-{index}", layer=layer, subject=subject,
            operator=operator, expected=expected, confidence=confidence,
            source=f'expected_text:"{text[:40]}" + {layer}:{subject}',
            evidence_refs=evidence_refs, notes=notes,
        ))

    # DB 侧:库约束派生正向"存在性"Oracle(被测字段应落库),与 adversarial 的负向互补
    for column, meta in (db_constraints or {}).items():
        if not isinstance(meta, dict) or not meta.get("required"):
            continue
        index += 1
        enum_values = meta.get("enum") or []
        if enum_values:
            operator, expected, expected_known = "in", list(enum_values), True
        else:
            operator, expected, expected_known = "exists", None, False
        candidates.append(OracleCandidate(
            id=f"auto-db-{index}", layer="db", subject=column,
            operator=operator, expected=expected,
            confidence=score(pattern_hit=False, subject_found=True,
                             expected_known=expected_known, mapping_supported=False),
            source=f"db_constraint:{column}(required)",
            evidence_refs=[f"db_intel:{column}"],
            notes=([] if expected_known else ["expected 为存在性校验,精确值需人工确认"]),
        ))

    return [candidate.to_dict() for candidate in candidates]


def summarize(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """候选分桶:高/中/低置信,给人审排序与提示。"""
    high = [c for c in candidates if c["confidence"] >= HIGH_CONFIDENCE]
    low = [c for c in candidates if c["confidence"] < LOW_CONFIDENCE]
    mid = [c for c in candidates if c not in high and c not in low]
    return {"total": len(candidates), "high": high, "mid": mid, "low": low}

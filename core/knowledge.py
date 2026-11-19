"""Persistent, scoped project knowledge used by planning and execution.

Knowledge is deliberately conservative: discovery can create pending records,
but only approved records may affect a formal execution plan.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any, Iterable


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_APPROVED = {"approved", "human_verified"}
_KNOWLEDGE_DIRS = (
    "business_rules", "operating_procedures", "page_models", "api_contracts",
    "data_mappings", "state_recipes", "role_resolution", "cleanup_recipes",
    "environment_facts", "troubleshooting", "decisions", "conflicts",
)


def content_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def record_hash(record: dict[str, Any]) -> str:
    value = json.loads(json.dumps(record, ensure_ascii=False))
    (value.get("governance") or {}).pop("content_hash", None)
    value.pop("verification", None)
    return content_hash(value)


def question_fingerprint(*parts: str) -> str:
    normalized = "|".join(" ".join(str(part or "").lower().split()) for part in parts)
    return content_hash(normalized)[:24]


def _knowledge_id(value: str) -> str:
    if not _SAFE_ID.fullmatch(value):
        raise ValueError(f"unsafe knowledge_id: {value!r}")
    return value


class KnowledgeBase:
    """Workspace knowledge index with approval and stale/conflict guards."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self._records: dict[str, dict[str, Any]] = {}
        self._by_question: dict[str, dict[str, Any]] = {}
        self._page_model: dict[str, dict[str, Any]] = {}
        self._data_mapping: dict[str, dict[str, Any]] = {}
        self._business_rules: list[dict[str, Any]] = []
        self._invalid_input_rules: list[dict[str, Any]] = []

    @property
    def knowledge_dir(self) -> Path:
        return self.root / "knowledge_base"

    def load(self) -> "KnowledgeBase":
        """Load both the new typed store and legacy knowledge files."""
        self._records.clear()
        self._by_question.clear()
        for directory in _KNOWLEDGE_DIRS:
            base = self.knowledge_dir / directory
            if not base.is_dir():
                continue
            for path in sorted(base.glob("*.json")):
                self._load_file(path)

        # Existing workspace layout remains readable during migration.
        self._load_legacy_dir("page_model", self._page_model)
        self._load_legacy_dir("data_mapping", self._data_mapping)
        self._load_legacy_json("business_rules.json", self._business_rules)
        self._load_legacy_json("invalid_input_rules.json", self._invalid_input_rules)
        return self

    def _load_file(self, path: Path) -> None:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        records = value if isinstance(value, list) else [value]
        for record in records:
            if not isinstance(record, dict):
                continue
            record_id = record.get("knowledge_id")
            if record_id:
                self._records[str(record_id)] = record
                fingerprint = (record.get("question") or {}).get("fingerprint")
                if fingerprint:
                    self._by_question[str(fingerprint)] = record

    def _load_legacy_dir(self, name: str, target: dict[str, dict[str, Any]]) -> None:
        base = self.knowledge_dir / name
        if not base.is_dir():
            return
        for path in base.glob("*.json"):
            try:
                target[path.stem] = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue

    def _load_legacy_json(self, name: str, target: list[dict[str, Any]]) -> None:
        path = self.knowledge_dir / name
        if not path.is_file():
            return
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if isinstance(value, list):
            target.extend(item for item in value if isinstance(item, dict))
        elif isinstance(value, dict):
            target.append(value)

    def records(self, *, status: str | None = None, kind: str | None = None) -> list[dict[str, Any]]:
        values = list(self._records.values())
        if status:
            values = [item for item in values if item.get("governance", {}).get("approval_status") == status]
        if kind:
            values = [item for item in values if item.get("type") == kind]
        return sorted(values, key=lambda item: str(item.get("knowledge_id", "")))

    def get(self, knowledge_id: str, *, approved_only: bool = False) -> dict[str, Any] | None:
        record = self._records.get(knowledge_id)
        if not record:
            return None
        if approved_only and not self.is_usable(record):
            return None
        return record

    def search(self, query: str, *, scope: dict[str, str] | None = None,
               approved_only: bool = True) -> list[dict[str, Any]]:
        terms = {part for part in re.findall(r"[\w\u4e00-\u9fff]+", query.lower()) if len(part) > 1}
        matches = []
        for record in self._records.values():
            if approved_only and not self.is_usable(record):
                continue
            if scope and not self.scope_matches(record, scope):
                continue
            haystack = json.dumps(record, ensure_ascii=False).lower()
            score = sum(term in haystack for term in terms)
            if score:
                matches.append((score, record))
        return [record for _, record in sorted(matches, key=lambda item: (-item[0], item[1].get("knowledge_id", "")))]

    def recommend_for_case(self, case: dict[str, Any], *, limit: int = 10) -> list[dict[str, Any]]:
        """Recommend approved knowledge without silently changing the case."""
        scope = {key: str(value) for key, value in {
            "project": case.get("suite_id"),
            "module": case.get("module") or (case.get("source") or {}).get("module"),
            "feature": (case.get("execution") or {}).get("feature"),
        }.items() if value}
        query_parts = [str(case.get("title") or ""), " ".join(case.get("business_tags") or [])]
        query_parts.extend(str(item) for item in case.get("open_questions") or [])
        results = self.search(" ".join(query_parts), scope=scope, approved_only=True)
        return [{"knowledge_id": item["knowledge_id"], "type": item.get("type"),
                 "confidence": (item.get("governance") or {}).get("confidence", 0),
                 "statement": item.get("statement", {})} for item in results[:limit]]

    def bind_recommendations(self, case: dict[str, Any], *, minimum_confidence: float = 0.8) -> dict[str, Any]:
        """Bind only approved, scoped, explicit compiled knowledge to a draft case."""
        from core.rule_compiler import apply_rule_knowledge
        recommended = self.recommend_for_case(case, limit=20)
        records = []
        for item in recommended:
            record = self.get(item["knowledge_id"], approved_only=True)
            confidence = float((record.get("governance") or {}).get("confidence") or 0)
            if record and confidence >= minimum_confidence and record.get("compiled"):
                records.append(record)
        return apply_rule_knowledge(case, records)

    def answer_for(self, fingerprint: str, *, scope: dict[str, str] | None = None) -> dict[str, Any] | None:
        record = self._by_question.get(fingerprint)
        if record and self.is_usable(record) and (not scope or self.scope_matches(record, scope)):
            return record
        return None

    def question_status(self, question: str, *, scope: dict[str, str] | None = None) -> dict[str, Any]:
        fingerprint = question_fingerprint(*(list((scope or {}).values()) + [question]))
        record = self._by_question.get(fingerprint)
        if not record:
            return {"fingerprint": fingerprint, "may_ask": True, "reason": "unknown", "knowledge": None}
        if self.is_usable(record) and (not scope or self.scope_matches(record, scope)):
            return {"fingerprint": fingerprint, "may_ask": False, "reason": "approved_answer_exists",
                    "knowledge": record}
        return {"fingerprint": fingerprint, "may_ask": True,
                "reason": "answer_pending_or_stale", "knowledge": record}

    def require_question(self, question: str, *, scope: dict[str, str] | None = None) -> str:
        """Return a fingerprint only when asking the user is still permitted."""
        status = self.question_status(question, scope=scope)
        if not status["may_ask"]:
            knowledge_id = status["knowledge"]["knowledge_id"]
            raise ValueError(f"repeated question blocked; use approved knowledge: {knowledge_id}")
        return str(status["fingerprint"])

    def is_usable(self, record: dict[str, Any]) -> bool:
        governance = record.get("governance") or {}
        if governance.get("approval_status") not in _APPROVED:
            return False
        if governance.get("stale") or governance.get("conflicted"):
            return False
        expires_at = governance.get("expires_at")
        return not expires_at or str(expires_at) > time.strftime("%Y-%m-%dT%H:%M:%S")

    @staticmethod
    def scope_matches(record: dict[str, Any], scope: dict[str, str]) -> bool:
        values = record.get("scope") or {}
        return all(not values.get(key) or values.get(key) == value for key, value in scope.items())

    def page_model(self, feature: str) -> dict[str, Any]:
        return self._page_model.get(feature, {})

    def data_mapping(self, feature: str) -> dict[str, Any]:
        return self._data_mapping.get(feature, {})

    def write_pending(self, record: dict[str, Any]) -> Path:
        """Persist a candidate knowledge record without making it executable."""
        value = dict(record)
        record_id = _knowledge_id(str(value.get("knowledge_id") or f"K-{int(time.time() * 1000)}"))
        value["knowledge_id"] = record_id
        value.setdefault("schema_version", 1)
        value.setdefault("created_at", time.strftime("%Y-%m-%dT%H:%M:%S"))
        value.setdefault("governance", {})
        value["governance"].setdefault("approval_status", "pending")
        conflicts = self.detect_conflicts(value)
        if conflicts and not value["governance"].get("conflict_resolved"):
            value["governance"]["conflicted"] = True
            value["governance"]["conflicts_with"] = [item["knowledge_id"] for item in conflicts]
        value["governance"].pop("content_hash", None)
        value["governance"]["content_hash"] = record_hash(value)
        directory = str(value.get("storage_kind") or value.get("type") or "decisions")
        if directory not in _KNOWLEDGE_DIRS:
            directory = "decisions"
        path = self.knowledge_dir / directory / f"{record_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self._records[record_id] = value
        fingerprint = (value.get("question") or {}).get("fingerprint")
        if fingerprint:
            self._by_question[str(fingerprint)] = value
        return path

    def record_answer(self, *, question: str, answer: str, scope: dict[str, str] | None = None,
                      source: dict[str, Any] | None = None, knowledge_type: str = "business_rule",
                      knowledge_id: str | None = None) -> dict[str, Any]:
        """Store a user answer as pending knowledge and return the saved record."""
        fingerprint = question_fingerprint(*(list((scope or {}).values()) + [question]))
        record = {
            "knowledge_id": knowledge_id or f"K-Q-{fingerprint}",
            "type": knowledge_type,
            "scope": scope or {},
            "question": {"fingerprint": fingerprint, "text": question},
            "statement": {"natural_language": answer},
            "source": {"type": "user_confirmed_candidate", **(source or {})},
            "governance": {"approval_status": "pending", "mandatory": True, "confidence": 0.7},
        }
        self.write_pending(record)
        return record

    def approve(self, knowledge_id: str, *, approver: str = "human") -> Path:
        record = self.get(knowledge_id)
        if not record:
            raise KeyError(knowledge_id)
        record = dict(record)
        governance = dict(record.get("governance") or {})
        governance.update({"approval_status": "approved", "approved_by": approver,
                           "approved_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "stale": False})
        record["governance"] = governance
        return self.write_pending(record)

    def mark_stale(self, knowledge_id: str, *, reason: str) -> Path:
        record = self.get(knowledge_id)
        if not record:
            raise KeyError(knowledge_id)
        value = dict(record)
        governance = dict(value.get("governance") or {})
        governance.update({"stale": True, "stale_reason": reason,
                           "stale_at": time.strftime("%Y-%m-%dT%H:%M:%S")})
        value["governance"] = governance
        return self.write_pending(value)

    def supersede(self, old_id: str, new_id: str, *, approver: str = "human") -> list[Path]:
        old = self.get(old_id)
        new = self.get(new_id)
        if not old or not new:
            raise KeyError(old_id if not old else new_id)
        new_value = dict(new)
        new_governance = dict(new_value.get("governance") or {})
        new_governance.update({"approval_status": "approved", "approved_by": approver,
                               "approved_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                               "supersedes": old_id, "stale": False, "conflicted": False,
                               "conflict_resolved": True})
        new_value["governance"] = new_governance
        old_value = dict(old)
        old_governance = dict(old_value.get("governance") or {})
        old_governance.update({"stale": True, "superseded_by": new_id,
                               "stale_reason": "superseded"})
        old_value["governance"] = old_governance
        return [self.write_pending(new_value), self.write_pending(old_value)]

    def conflicts(self) -> list[dict[str, Any]]:
        return [record for record in self._records.values()
                if (record.get("governance") or {}).get("conflicted")]

    def detect_conflicts(self, candidate: dict[str, Any]) -> list[dict[str, Any]]:
        fingerprint = (candidate.get("question") or {}).get("fingerprint")
        if not fingerprint:
            return []
        answer = (candidate.get("statement") or {}).get("natural_language")
        return [record for record in self._records.values()
                if record.get("knowledge_id") != candidate.get("knowledge_id")
                and (record.get("question") or {}).get("fingerprint") == fingerprint
                and (record.get("statement") or {}).get("natural_language") != answer
                and self.is_usable(record)]

    def capture_run_feedback(self, knowledge_ids: Iterable[str], *, ok: bool,
                             run_id: str = "") -> list[Path]:
        """Record deterministic execution feedback without changing rule content."""
        paths = []
        for knowledge_id in knowledge_ids:
            record = self.get(str(knowledge_id))
            if not record:
                continue
            value = dict(record)
            verification = dict(value.get("verification") or {})
            key = "success_count" if ok else "failure_count"
            verification[key] = int(verification.get(key) or 0) + 1
            verification["last_verified_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            if run_id:
                runs = list(verification.get("verified_runs") or [])
                if run_id not in runs:
                    runs.append(run_id)
                verification["verified_runs"] = runs[-20:]
            value["verification"] = verification
            if not ok and verification["failure_count"] >= 3:
                governance = dict(value.get("governance") or {})
                governance.update({"stale": True, "stale_reason": "three execution failures",
                                   "stale_at": time.strftime("%Y-%m-%dT%H:%M:%S")})
                value["governance"] = governance
            paths.append(self.write_pending(value))
        return paths

    def learn_failure(self, *, case_id: str, category: str, details: list[str],
                      scope: dict[str, str] | None = None, run_id: str = "") -> Path:
        """Persist a non-secret failure signature as pending troubleshooting knowledge."""
        signature = question_fingerprint(case_id, category, "|".join(details[:3]))
        return self.write_pending({
            "knowledge_id": f"K-TS-{signature}",
            "type": "troubleshooting",
            "storage_kind": "troubleshooting",
            "scope": scope or {},
            "statement": {"category": category, "symptoms": details[:10]},
            "source": {"type": "execution_failure", "case_id": case_id, "run_id": run_id},
            "governance": {"approval_status": "pending", "mandatory": False, "confidence": 0.4},
        })

    def write_back_pending(self, feature: str, discovered: dict[str, Any]) -> Path:
        value = dict(discovered)
        value.setdefault("scope", {})["feature"] = feature
        value.setdefault("source", {})["type"] = "auto_discovered"
        return self.write_pending(value)

    def dependency(self, knowledge_id: str) -> dict[str, Any]:
        record = self.get(knowledge_id, approved_only=True)
        if not record:
            raise ValueError(f"knowledge is not approved or is stale: {knowledge_id}")
        return {"knowledge_id": knowledge_id,
                "version": record.get("version", 1),
                "content_hash": record_hash(record)}

    def dependencies(self, ids: Iterable[str]) -> list[dict[str, Any]]:
        return [self.dependency(str(item)) for item in ids]

"""Business-neutral onboarding models and deterministic planning primitives.

Business facts belong in profiles, connectors, capability packs, bindings,
fixtures, and oracle configuration. This module only defines the contracts
between those assets.
"""
from __future__ import annotations

import hashlib
import json
import re
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml

from core.case_source import read_cases
from core.suite_plan import classify_case

SCHEMA_VERSION = 1
GAP_TYPES = (
    "CAPABILITY_MISSING",
    "BUSINESS_INPUT_REQUIRED",
    "ENVIRONMENT_MISSING",
    "FIXTURE_MISSING",
    "BINDING_REVIEW_REQUIRED",
    "ORACLE_REVIEW_REQUIRED",
    "MANUAL_ONLY",
)
LAYERS = ("ui", "api", "db", "auth", "async", "mq", "job")


def _stable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _stable(value[k]) for k in sorted(value)}
    if isinstance(value, (list, tuple, set)):
        return [_stable(item) for item in value]
    return value


def fingerprint(value: Any) -> str:
    payload = json.dumps(_stable(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_document(path: str | Path) -> Any:
    target = Path(path)
    if target.is_dir():
        documents = []
        for item in sorted(target.rglob("*")):
            if item.is_file() and item.suffix.lower() in {".json", ".yaml", ".yml", ".md", ".txt"}:
                documents.append({"path": item.relative_to(target).as_posix(), "content": item.read_text(encoding="utf-8")})
        return documents
    if target.suffix.lower() == ".json":
        return json.loads(target.read_text(encoding="utf-8"))
    if target.suffix.lower() in {".yaml", ".yml"}:
        return yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    if target.suffix.lower() in {".md", ".txt"}:
        return {"path": target.name, "content": target.read_text(encoding="utf-8")}
    content = target.read_bytes()
    return {"path": target.name, "size": len(content), "sha256": hashlib.sha256(content).hexdigest()}


class InputAdapter(ABC):
    """Convert an external case source into business-neutral canonical cases."""

    @abstractmethod
    def read(self, source: str | Path, suite_id: str) -> list["CanonicalCase"]:
        raise NotImplementedError


class TabularInputAdapter(InputAdapter):
    def read(self, source: str | Path, suite_id: str) -> list["CanonicalCase"]:
        return canonicalize(source, suite_id)


@dataclass
class CanonicalCase:
    case_id: str
    title: str
    source_key: str
    priority: str
    intents: list[str]
    required_layers: list[str]
    preconditions: str = ""
    steps: str = ""
    expected: str = ""
    source_row: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": SCHEMA_VERSION, **asdict(self)}


@dataclass
class CapabilityGraph:
    capabilities: list[dict[str, Any]] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": SCHEMA_VERSION, "capabilities": self.capabilities, "edges": self.edges}


@dataclass
class CoverageRequirement:
    case_id: str
    layer: str
    requirement_id: str
    status: str
    gap_type: str | None = None
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FixtureRequirement:
    fixture_id: str
    consumers: list[str]
    source_condition: str
    strategy_candidates: list[str]
    preferred_strategy: str | None
    cleanup_required: bool
    missing_inputs: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BindingCandidate:
    candidate_id: str
    case_id: str
    layer: str
    target_kind: str
    target: str
    confidence: float
    status: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OraclePlan:
    oracle_id: str
    case_id: str
    layer: str
    oracle_kind: str
    status: str
    missing_inputs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExecutionReadiness:
    case_id: str
    status: str
    required_layers: list[str]
    blocking_gaps: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GapReport:
    gaps: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        counts = {kind: sum(item.get("type") == kind for item in self.gaps) for kind in GAP_TYPES}
        return {"schema_version": SCHEMA_VERSION, "total": len(self.gaps), "counts": counts, "gaps": self.gaps}


def validate_document(value: Any, schema: dict[str, Any]) -> list[str]:
    """Validate the framework's supported JSON Schema subset deterministically."""
    errors: list[str] = []
    if schema.get("type") == "object" and not isinstance(value, dict):
        return ["$: expected object"]
    for key in schema.get("required") or []:
        if key not in value:
            errors.append(f"$.{key}: required property missing")
    properties = schema.get("properties") or {}
    for key, rule in properties.items():
        if key not in value:
            continue
        item = value[key]
        expected = rule.get("type")
        if expected == "array" and not isinstance(item, list):
            errors.append(f"$.{key}: expected array")
        elif expected == "object" and not isinstance(item, dict):
            errors.append(f"$.{key}: expected object")
        elif expected == "string" and not isinstance(item, str):
            errors.append(f"$.{key}: expected string")
        elif expected == "integer" and (not isinstance(item, int) or isinstance(item, bool)):
            errors.append(f"$.{key}: expected integer")
        elif expected == "number" and (not isinstance(item, (int, float)) or isinstance(item, bool)):
            errors.append(f"$.{key}: expected number")
        elif expected == "boolean" and not isinstance(item, bool):
            errors.append(f"$.{key}: expected boolean")
    return errors


def canonicalize(source: str | Path, suite_id: str) -> list[CanonicalCase]:
    if Path(source).suffix.lower() not in {".xlsx", ".xlsm", ".csv", ".json"}:
        raise ValueError("cases must be an .xlsx, .xlsm, .csv, or .json file")
    result = []
    for raw in read_cases(source):
        classified = classify_case(raw)
        key = str(raw.case_id or f"row-{raw.row}")
        result.append(CanonicalCase(
            case_id=f"{suite_id}/{key}-{raw.row}", title=str(raw.name or key), source_key=key,
            priority=str(raw.level or "P2"), intents=list(classified["intents"]),
            required_layers=list(classified["required_layers"]), preconditions=str(raw.preconditions or ""),
            steps=str(raw.steps_text or ""), expected=str(raw.expected_text or ""), source_row=raw.row,
        ))
    return result


def build_capability_graph(profile: dict[str, Any], workspace: Path) -> CapabilityGraph:
    capabilities = []
    configured = profile.get("capabilities") or profile.get("capability_pack") or []
    if isinstance(configured, dict):
        configured = [{"id": key, **(value if isinstance(value, dict) else {"value": value})}
                      for key, value in configured.items()]
    for item in configured:
        if isinstance(item, str):
            item = {"id": item}
        capabilities.append({"id": str(item.get("id") or item.get("name") or "unknown"),
                             "layers": sorted(set(item.get("layers") or [])),
                             "source": "profile", "status": str(item.get("status") or "declared")})
    if profile.get("base_url"):
        capabilities.extend([
            {"id": "environment.web", "layers": ["ui"], "source": "profile", "status": "configured"},
            {"id": "environment.http", "layers": ["api"], "source": "profile", "status": "configured"},
        ])
    if profile.get("db"):
        capabilities.append({"id": "environment.database", "layers": ["db"], "source": "profile", "status": "configured"})
    if profile.get("login"):
        capabilities.append({"id": "environment.identity", "layers": ["auth"], "source": "profile", "status": "configured"})
    knowledge = workspace / "knowledge_base"
    if knowledge.exists():
        for path in sorted(knowledge.rglob("*.json")):
            capabilities.append({"id": f"knowledge.{path.stem}", "layers": [], "source": "workspace", "status": "discovered"})
    unique = {item["id"]: item for item in capabilities}
    return CapabilityGraph(capabilities=list(unique.values()), edges=[])


def _layer_assets(profile: dict[str, Any], layer: str) -> list[str]:
    bindings = profile.get("bindings") or {}
    value = bindings.get(layer) if isinstance(bindings, dict) else None
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def load_suite_assets(suite_dir: str | Path | None) -> dict[str, Any]:
    """Index reviewed suite-local assets without embedding their business meaning."""
    if not suite_dir:
        return {"fixtures": {}, "bindings": {}, "oracles": {}, "source": ""}
    root = Path(suite_dir)
    result: dict[str, Any] = {"fixtures": {}, "bindings": {}, "oracles": {}, "source": str(root),
                              "fingerprint": ""}
    fixture_path = root / "fixtures.yaml"
    if fixture_path.exists():
        registry = yaml.safe_load(fixture_path.read_text(encoding="utf-8")) or {}
        for fixture_id, fixture in (registry.get("fixtures") or {}).items():
            for case_key in fixture.get("case_keys") or []:
                result["fixtures"][str(case_key)] = {
                    "fixture_id": str(fixture_id), "verified": bool(fixture.get("verified")),
                    "source": str(fixture.get("source") or fixture_path.name),
                }
    for directory in (root / "ui_bindings", root / "generated_specs", root / "specs"):
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.yaml")):
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            case_key = str(data.get("canonical_case_key") or data.get("case_id") or path.stem).split("-UI", 1)[0]
            layers = []
            if data.get("ui") or data.get("mode") == "ui":
                layers.append("ui")
            if data.get("request") or data.get("mode") in {"api", "write", "reconcile"}:
                layers.append("api")
            assertions = data.get("assertions") or data.get("engine_assertions") or {}
            if data.get("db") or (isinstance(assertions, dict) and assertions.get("db")):
                layers.append("db")
            verified = str(data.get("verify_status") or "").lower() in {"human_verified", "approved", "verified"}
            for layer in set(layers):
                result["bindings"].setdefault(case_key, {})[layer] = {
                    "target": str(path), "verified": verified,
                    "health": str(data.get("binding_health") or "verified"),
                }
                if assertions:
                    result["oracles"].setdefault(case_key, {})[layer] = {
                        "source": str(path), "verified": verified,
                    }
    asset_files = [fixture_path] if fixture_path.exists() else []
    for directory in (root / "ui_bindings", root / "generated_specs", root / "specs"):
        if directory.exists():
            asset_files.extend(path for path in directory.glob("*.yaml") if path.is_file())
    result["fingerprint"] = fingerprint({
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(set(asset_files))
    })
    return result


def _gap(case_id: str, layer: str, kind: str, reason: str) -> dict[str, Any]:
    if kind not in GAP_TYPES:
        raise ValueError(f"unsupported gap type: {kind}")
    return {"case_id": case_id, "gap_id": f"gap:{case_id}:{layer}:{kind.lower()}",
            "type": kind, "layer": layer, "reason": reason}


def plan_onboarding(cases: list[CanonicalCase], graph: CapabilityGraph, profile: dict[str, Any],
                    suite_assets: dict[str, Any] | None = None) -> dict[str, Any]:
    suite_assets = suite_assets or {"fixtures": {}, "bindings": {}, "oracles": {}}
    available = {layer for item in graph.capabilities for layer in item.get("layers", [])}
    coverage, bindings, fixtures, oracles, readiness, gaps = [], [], [], [], [], []
    grouped: dict[str, list[str]] = {}
    for case in cases:
        condition = re.sub(r"\s+", " ", case.preconditions.strip().lower()) or "none"
        grouped.setdefault(condition, []).append(case.case_id)
        case_gaps = []
        for layer in case.required_layers or ["api"]:
            if layer == "manual":
                item = _gap(case.case_id, layer, "MANUAL_ONLY", "case requires a human-only verification step")
                coverage.append(CoverageRequirement(case.case_id, layer, f"{case.case_id}:{layer}",
                                                    "MANUAL", "MANUAL_ONLY", item["reason"]).to_dict())
                case_gaps.append(item)
                continue
            ok = layer in available
            gap_type = None if ok else "ENVIRONMENT_MISSING"
            requirement = CoverageRequirement(f"{case.case_id}:{layer}", layer, f"{case.case_id}:{layer}",
                                               "SATISFIED" if ok else "MISSING", gap_type,
                                               "declared capability available" if ok else "required layer is not configured")
            coverage.append(requirement.to_dict())
            if not ok:
                case_gaps.append(_gap(case.case_id, layer, gap_type, requirement.reason))
            imported_binding = ((suite_assets.get("bindings") or {}).get(case.source_key) or {}).get(layer)
            targets = ([imported_binding["target"]] if imported_binding else []) or _layer_assets(profile, layer)
            imported_verified = bool(imported_binding and imported_binding.get("verified"))
            binding_status = "REVIEWED" if imported_verified else ("CANDIDATE" if targets else "REVIEW_REQUIRED")
            bindings.append(BindingCandidate(f"binding:{case.case_id}:{layer}", case.case_id, layer,
                                              f"{layer}_target", targets[0] if targets else "",
                                              1.0 if imported_verified else (0.6 if targets else 0.0),
                                              binding_status).to_dict())
            if ok and not imported_verified:
                case_gaps.append(_gap(case.case_id, layer, "BINDING_REVIEW_REQUIRED",
                                      "candidate target requires review" if targets else
                                      "capability exists but no reviewed target binding is available"))
            oracle_kind = "cross_layer_reconciliation" if len(case.required_layers) > 1 else f"{layer}_response"
            oracle_config = profile.get("oracles") or {}
            imported_oracle = ((suite_assets.get("oracles") or {}).get(case.source_key) or {}).get(layer)
            oracle_ready = bool(imported_oracle and imported_oracle.get("verified")) or (
                isinstance(oracle_config, dict) and bool(oracle_config.get(layer)))
            oracles.append(OraclePlan(f"oracle:{case.case_id}:{layer}", case.case_id, layer, oracle_kind,
                                      "CONFIGURED" if oracle_ready else "REVIEW_REQUIRED",
                                      [] if oracle_ready else ["expected business outcome"]).to_dict())
            if ok and not oracle_ready:
                case_gaps.append(_gap(case.case_id, layer, "ORACLE_REVIEW_REQUIRED",
                                      "expected outcome requires reviewed oracle configuration"))
        readiness.append(ExecutionReadiness(case.case_id, "READY" if not case_gaps else "BLOCKED",
                                            case.required_layers, case_gaps).to_dict())
        gaps.extend(case_gaps)
    for condition, consumers in sorted(grouped.items()):
        recipes = profile.get("fixture_recipes") or {}
        consumer_keys = {case.case_id: case.source_key for case in cases}
        imported = [((suite_assets.get("fixtures") or {}).get(consumer_keys[case_id]) or {})
                    for case_id in consumers]
        imported_verified = [item for item in imported if item.get("verified")]
        configured = (isinstance(recipes, dict) and condition in recipes) or bool(imported_verified)
        preferred = str(recipes.get(condition)) if configured else None
        if imported_verified:
            preferred = f"suite_asset:{imported_verified[0]['fixture_id']}"
        fixtures.append(FixtureRequirement(f"fixture:{fingerprint(condition)[:12]}", sorted(consumers), condition,
                                           ["api_workflow", "database_seed", "state_transition", "manual"],
                                           preferred, True, [] if configured or condition == "none" else
                                           ["fixture strategy and required business state"]).to_dict())
        if condition != "none" and not configured:
            for case_id in sorted(consumers):
                item = _gap(case_id, "fixture", "FIXTURE_MISSING",
                            "precondition has no approved shared fixture recipe")
                gaps.append(item)
                record = next(entry for entry in readiness if entry["case_id"] == case_id)
                record["blocking_gaps"].append(item)
                record["status"] = "BLOCKED"
    return {"coverage_matrix": coverage, "binding_candidates": bindings, "fixture_requirements": fixtures,
            "oracle_plan": oracles, "readiness": readiness, "gap_report": GapReport(gaps).to_dict()}


def schemas() -> dict[str, dict[str, Any]]:
    base = {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"}
    return {
        "canonical_case": {**base, "required": ["schema_version", "case_id", "title", "required_layers"],
                           "properties": {"schema_version": {"type": "integer"}, "case_id": {"type": "string"},
                                          "title": {"type": "string"}, "required_layers": {"type": "array"}}},
        "capability_graph": {**base, "required": ["schema_version", "capabilities", "edges"]},
        "coverage_requirement": {**base, "required": ["case_id", "layer", "requirement_id", "status"]},
        "fixture_requirement": {**base, "required": ["fixture_id", "consumers", "strategy_candidates"]},
        "binding_candidate": {**base, "required": ["candidate_id", "case_id", "layer", "status"]},
        "oracle_plan": {**base, "required": ["oracle_id", "case_id", "layer", "status"]},
        "execution_readiness": {**base, "required": ["case_id", "status", "blocking_gaps"]},
        "gap_report": {**base, "required": ["schema_version", "total", "counts", "gaps"]},
        "gap_resolutions": {**base, "required": ["schema_version", "resolutions"],
                            "properties": {"schema_version": {"type": "integer"},
                                           "resolutions": {"type": "array"}}},
    }

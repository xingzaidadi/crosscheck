"""Cross-layer contract checks (generic, zero-business): request-vs-response-vs-dictionary.

Derived from live crosscheck runs where UI-tab contracts diverged from backend behaviour:
  1. A list endpoint applies NO default filter; each UI tab carries its own request params.
     If the frontend omits/mis-sends the filter, out-of-scope records leak into the view and
     the backend does not guard it. -> check_default_filter_leak
  2. A request declares an enum filter value that the backend's real value dictionary does
     not contain ("dangling enum" / dictionary drift). Harmless only while no such data
     exists today; unverified the moment it is written. -> check_dangling_enum
  3. A paginated response must satisfy page invariants (stable total across page sizes,
     pages == ceil(total/pageSize), returned rows == min(pageSize, remaining)).
     -> check_pagination_invariants
  4. An error response must carry a transport status consistent with being an error: a
     body that reports failure must not ride on a 2xx (masked error), and a client/validation
     error must not surface as 5xx (server-fault status for a caller-fixable error).
     -> check_error_status_contract

All functions take abstract request/response/dictionary structures only — no domain terms,
no field names baked in — so they stay portable under the core zero-business gate. They are
soft-gate: they return findings/candidates, never mutate a verdict or reject.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil
from typing import Any


@dataclass
class ContractFinding:
    check: str
    severity: str  # "contract-risk" | "spec-insight" | "info"
    detail: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"check": self.check, "severity": self.severity,
                "detail": self.detail, "evidence": self.evidence}


def check_dangling_enum(requested_values: list[Any],
                        backend_dictionary: list[Any]) -> list[ContractFinding]:
    """Flag any enum value the frontend requests that the backend dictionary does not define.

    requested_values: enum values present in the real request (e.g. a category filter array).
    backend_dictionary: the set of enum values the backend actually recognises/returns.
    """
    known = set(backend_dictionary)
    dangling = [v for v in requested_values if v not in known]
    findings: list[ContractFinding] = []
    for value in dangling:
        findings.append(ContractFinding(
            check="dangling_enum",
            severity="contract-risk",
            detail=f"requested enum {value!r} not in backend dictionary",
            evidence={"value": value, "backend_dictionary": sorted(map(str, known))},
        ))
    return findings


def check_default_filter_leak(unfiltered_value_set: list[Any],
                              tab_declared_scope: list[Any]) -> list[ContractFinding]:
    """Detect that an endpoint without a filter returns values beyond a tab's declared scope.

    unfiltered_value_set: distinct values a no-filter call returns (proves no default guard).
    tab_declared_scope: the value(s) a given tab claims to show.
    A non-empty leak means: omit the tab's filter and out-of-scope records surface.
    """
    scope = set(tab_declared_scope)
    leaked = sorted({str(v) for v in unfiltered_value_set if v not in scope})
    if not leaked:
        return []
    return [ContractFinding(
        check="default_filter_leak",
        severity="contract-risk",
        detail="endpoint has no default filter; omitting the tab filter leaks out-of-scope records",
        evidence={"declared_scope": sorted(map(str, scope)), "leaked_values": leaked},
    )]


def check_pagination_invariants(pages_meta: list[dict[str, Any]]) -> list[ContractFinding]:
    """Verify page invariants across >=1 page reads of the SAME query at different page sizes.

    Each entry: {"pageSize": int, "pageNum": int, "total": int, "pages": int, "returned": int}.
    Invariants:
      - total is stable across all reads of the same query,
      - pages == ceil(total / pageSize),
      - returned == min(pageSize, total - (pageNum-1)*pageSize)   (clamped at 0).
    """
    findings: list[ContractFinding] = []
    totals = {m["total"] for m in pages_meta}
    if len(totals) > 1:
        findings.append(ContractFinding(
            check="pagination_total_unstable", severity="contract-risk",
            detail="total differs across page reads of the same query",
            evidence={"totals": sorted(totals)}))
    for m in pages_meta:
        ps, pn, total = m["pageSize"], m.get("pageNum", 1), m["total"]
        expected_pages = ceil(total / ps) if ps else 0
        if "pages" in m and m["pages"] != expected_pages:
            findings.append(ContractFinding(
                check="pagination_pages_wrong", severity="contract-risk",
                detail=f"pages={m['pages']} but ceil(total/pageSize)={expected_pages}",
                evidence={"pageSize": ps, "total": total, "reported_pages": m["pages"]}))
        expected_rows = max(0, min(ps, total - (pn - 1) * ps))
        if "returned" in m and m["returned"] != expected_rows:
            findings.append(ContractFinding(
                check="pagination_rows_wrong", severity="contract-risk",
                detail=f"returned={m['returned']} but expected {expected_rows}",
                evidence={"pageSize": ps, "pageNum": pn, "total": total, "returned": m["returned"]}))
    return findings


def check_error_status_contract(error_samples: list[dict[str, Any]]) -> list[ContractFinding]:
    """Verify that error responses carry a transport status consistent with being an error.

    Each sample describes ONE failed call against a backend endpoint:
      {"id": str, "http_status": int, "success": bool, "param_error": bool|None}
      - http_status: the transport status line the backend returned,
      - success: the body-level success flag (False == the call failed),
      - param_error: True if the failure is a client input/validation error (optional).
    Two transport-vs-body contract violations are flagged (all portable, no field names):
      - masked_error: body says it failed (success is False) but http_status is 2xx, so a
        caller that only inspects the status line mistakes failure for success.
      - client_error_as_server: a client/validation failure (param_error) surfaces as 5xx
        instead of 4xx, hiding a caller-fixable error behind a server-fault status.
    """
    findings: list[ContractFinding] = []
    for s in error_samples:
        if s.get("success") is True:
            continue  # only inspect failed calls
        http = s.get("http_status")
        ident = s.get("id", "?")
        if isinstance(http, int) and 200 <= http < 300:
            findings.append(ContractFinding(
                check="error_masked_as_success", severity="contract-risk",
                detail=f"{ident}: body reports failure but http status is {http} (2xx)",
                evidence={"id": ident, "http_status": http}))
        if s.get("param_error") is True and isinstance(http, int) and 500 <= http < 600:
            findings.append(ContractFinding(
                check="client_error_as_server", severity="contract-risk",
                detail=f"{ident}: client/validation error returned as {http} (5xx), expected 4xx",
                evidence={"id": ident, "http_status": http}))
    return findings


def run_contract_checks(spec: dict[str, Any]) -> dict[str, Any]:
    """Run all applicable checks from an abstract spec; soft-gate (report only).

    spec keys (all optional):
      - dangling_enum: {"requested": [...], "dictionary": [...]}
      - default_filter_leak: {"unfiltered": [...], "scope": [...]}
      - pagination: [ {pageSize,pageNum,total,pages,returned}, ... ]
      - error_status: [ {id,http_status,success,param_error}, ... ]
    """
    findings: list[ContractFinding] = []
    if "dangling_enum" in spec:
        d = spec["dangling_enum"]
        findings += check_dangling_enum(d.get("requested") or [], d.get("dictionary") or [])
    if "default_filter_leak" in spec:
        d = spec["default_filter_leak"]
        findings += check_default_filter_leak(d.get("unfiltered") or [], d.get("scope") or [])
    if "pagination" in spec:
        findings += check_pagination_invariants(spec["pagination"] or [])
    if "error_status" in spec:
        findings += check_error_status_contract(spec["error_status"] or [])
    return {
        "consistent": len(findings) == 0,
        "finding_count": len(findings),
        "findings": [f.to_dict() for f in findings],
    }

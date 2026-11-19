"""Unified URL + case-file UI runner with workspace skill discovery."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.business_skill import match_skill, write_context  # noqa: E402
from core.case_source import read_cases  # noqa: E402
from core.profile import list_profiles, load_profile  # noqa: E402
from core.config import site_credentials  # noqa: E402
from core.login import ensure_session, LoginError  # noqa: E402
from core.workspace import set_workspace  # noqa: E402
from scripts.ui_test import run as run_legacy  # noqa: E402
from scripts.render_ui_report import render_summary  # noqa: E402
from core.ui_test_intake import build_ui_intent  # noqa: E402


def _profile_for_url(workspace: Path, url: str):
    from urllib.parse import urlparse
    host = urlparse(url).netloc.lower()
    candidates = []
    for name in list_profiles():
        try:
            profile = load_profile(name)
        except (OSError, ValueError):
            continue
        if profile.base_url and urlparse(profile.base_url).netloc.lower() == host:
            score = 1
            probe_url = str((profile.defaults or {}).get("probe_url") or "")
            if probe_url and urlparse(probe_url).path and urlparse(url).path.startswith(urlparse(probe_url).path):
                score += 10 + len(urlparse(probe_url).path)
            candidates.append((score, profile))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def _prepare_auto_binding_candidates(cases_file: Path, url: str, workspace: Path) -> dict:
    """Persist conservative semantic action/oracle candidates for each source case."""
    from core.asset_store import AssetStore
    from core.asset_pipeline import create_candidate

    store = AssetStore(workspace / "knowledge_base" / "asset_candidates")
    rows = []
    for raw in read_cases(cases_file):
        intent = build_ui_intent(raw, url)
        actions = intent.actions
        oracles = [oracle.to_dict() for oracle in intent.oracles]
        action_candidate = create_candidate({
            "case_id": raw.case_id, "title": raw.name, "page_url": intent.page_url,
            "actions": actions, "write_risk": intent.write_risk,
            "source_steps": intent.source_steps,
            "required_review": ["page_entry", "action_semantics", "replay"],
        }, asset_type="ui_binding_candidate")
        store.save(action_candidate)
        oracle_candidate = create_candidate({
            "case_id": raw.case_id, "title": raw.name, "oracles": oracles,
            "unresolved_expectations": intent.unresolved_expectations,
            "required_review": ["oracle_semantics", "proof", "coverage"],
        }, asset_type="ui_oracle_candidate")
        store.save(oracle_candidate)
        rows.append({"case_id": raw.case_id, "actions": len(actions), "oracles": len(oracles),
                     "unresolved": intent.unresolved_expectations,
                     "action_candidate": action_candidate["asset_id"],
                     "oracle_candidate": oracle_candidate["asset_id"],
                     "auto_executable_read_only": bool(actions or oracles) and not intent.write_risk
                     and not intent.unresolved_expectations})
    return {"cases": rows, "candidate_count": len(rows) * 2}


def _run_canonical_pilot(cases_file: Path, workspace: Path, suite_id: str, profile: str,
                         run_id: str) -> dict | None:
    """Import source cases to an isolated suite and invoke the canonical UI pilot."""
    suite_path = workspace / "suites" / suite_id
    command = [sys.executable, str(ROOT / "scripts" / "import_suite.py"), str(cases_file),
               "--workspace", str(workspace), "--suite-id", suite_id]
    if profile:
        command.extend(["--profile", profile])
    imported = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
    if imported.returncode:
        return {"status": "IMPORT_FAILED", "stderr": imported.stderr, "stdout": imported.stdout}
    from scripts.ui_pilot import run as run_pilot
    pilot_args = argparse.Namespace(workspace=str(workspace), suite=str(suite_path), cases=str(cases_file),
                                    only=None, pilot_size=3, run_id=run_id, plan_only=False,
                                    no_session_refresh=False, no_resume=False)
    return run_pilot(pilot_args)


def main() -> int:
    parser = argparse.ArgumentParser(description="URL + 用例文件的一键 UI-first 测试入口")
    parser.add_argument("--cases", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--workspace", default="workspace")
    parser.add_argument("--session")
    parser.add_argument("--skill")
    parser.add_argument("--run-id")
    parser.add_argument("--only")
    parser.add_argument("--allow-write", action="store_true")
    parser.add_argument("--write-scope", help="写操作安全声明；必须明确测试数据、允许动作和清理策略")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--ensure-login", action="store_true",
                        help="兼容参数；匹配到 profile 时默认检活并续期登录态")
    parser.add_argument("--no-session-refresh", action="store_true",
                        help="仅复用现有登录态，不做检活或续期")
    parser.add_argument("--visual-baselines")
    parser.add_argument("--visual-threshold", type=float, default=0.0)
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    set_workspace(workspace)
    cases_path = Path(args.cases).resolve()
    if not cases_path.is_file():
        result = {"status": "NEEDS_INPUT", "missing_information": [
            {"field": "cases", "message": f"用例文件不存在：{cases_path}"}],
                  "run_id": args.run_id or f"ui_run_{time.strftime('%Y%m%d_%H%M%S')}",
                  "report": ""}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1
    skill = match_skill(workspace, args.url, skill_id=args.skill or "")
    profile = _profile_for_url(workspace, args.url)
    session = args.session or (profile.session_file if profile else "")
    session_action = "not_configured"
    if profile and not args.no_session_refresh:
        try:
            session = ensure_session(profile, site_credentials(profile.site), session_file=session)
            session_action = "reused_or_refreshed"
        except (LoginError, OSError, ValueError) as exc:
            session_action = f"blocked: {exc}"
    elif session and Path(session).is_file():
        session_action = "reused_existing_unchecked"
    elif session:
        session_action = "missing"
    context = {
        "url": args.url,
        "cases": str(Path(args.cases).resolve()),
        "workspace": str(workspace),
        "profile": profile.site if profile else "",
        "session": session,
        "business_skill": skill.context(args.url) if skill else None,
        "available_profiles": list_profiles(),
        "session_policy": "validate_then_reuse_or_refresh" if profile and not args.no_session_refresh
        else "reuse_existing_without_refresh",
        "session_action": session_action,
    }
    run_id = args.run_id or f"ui_run_{time.strftime('%Y%m%d_%H%M%S')}"
    binding_candidates = _prepare_auto_binding_candidates(cases_path, args.url, workspace)
    run_dir = workspace / "reports" / "ui-tests" / run_id
    context_path = write_context(run_dir / "context.json", context)
    forwarded = argparse.Namespace(
        cases=args.cases, url=args.url, workspace=args.workspace, session=session or None,
        run_id=run_id, only=args.only, allow_write=args.allow_write,
        write_scope=args.write_scope, headed=args.headed,
        visual_baselines=args.visual_baselines, visual_threshold=args.visual_threshold,
        timeout_ms=20000, wait_ms=1000,
        business_skill=skill,
    )
    if session_action.startswith("blocked:") or session_action == "missing":
        from core.case_source import read_cases
        raw_cases = read_cases(Path(args.cases)) if Path(args.cases).is_file() else []
        wanted = {item.strip() for item in (args.only or "").split(",") if item.strip()}
        if wanted:
            raw_cases = [case for case in raw_cases if case.case_id in wanted or case.name in wanted]
        cases = [{"case_id": case.case_id, "title": case.name, "verdict": "BLOCKED",
                  "reason": f"登录准备失败：{session_action}",
                  "source_steps": case.steps_text, "source_expected": case.expected_text,
                  "source_preconditions": case.preconditions, "source_module": case.module,
                  "execution": {}, "acceptance": {"coverage": 0.0, "verdict": "NOT_RUN"},
                  "evidence": {}} for case in raw_cases]
        result = {"status": "BLOCKED", "mode": "ui-only", "phase": "ui",
                  "api_execution": "NOT_EXECUTED", "db_execution": "NOT_EXECUTED",
                  "run_id": run_id, "reason": session_action,
                  "counts": {"BLOCKED": len(cases)}, "cases": cases,
                  "report": str(run_dir / "report.html")}
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                               encoding="utf-8")
        render_summary(run_dir)
    else:
        result = run_legacy(forwarded)
        result["binding_candidates"] = binding_candidates
        result["canonical_pilot"] = {
            "status": "CANDIDATES_CREATED",
            "reason": "候选 binding/oracle 已生成；正式套件仍需回放证据和 human_verified 审批",
            "candidate_count": binding_candidates["candidate_count"],
        }
        result["formal_readiness"] = "PILOT_ONLY_REVIEW_REQUIRED_FOR_FORMAL_PASS"
        if skill:
            cases = result.get("cases") or []
            status = "HEALTHY" if cases and all(item.get("verdict") == "PASS" for item in cases) \
                else "DEGRADED" if cases else "UNVERIFIED"
            evidence = [str(Path(result["report"]).relative_to(workspace))] if result.get("report") else []
            skill.record_health(status=status, evidence=evidence, run_id=run_id)
    result["intake_context"] = str(context_path)
    result["business_skill"] = skill.context(args.url) if skill else None
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 1 if result.get("status") == "NEEDS_INPUT" else (
        1 if any(key in (result.get("counts") or {}) for key in ("FAIL", "ENV_ERROR")) else 0
    )


if __name__ == "__main__":
    raise SystemExit(main())

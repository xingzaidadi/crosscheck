"""Single intake command that creates a runnable UI onboarding workspace."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlparse

import yaml

from core.ui_application_model import seed_model, write_model


def _slug(value: str) -> str:
    result = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip()).strip("-").lower()
    return result or "system"


def onboard(*, workspace: str, system: str, url: str, cases: str,
            login_mode: str = "manual", roles: list[str] | None = None,
            allow_write: bool = False, cleanup: str = "") -> dict:
    root = Path(workspace).resolve()
    cases_path = Path(cases).resolve()
    if not cases_path.is_file():
        raise FileNotFoundError(cases_path)
    site = _slug(system)
    profile_path = root / "profiles" / f"{site}.yaml"
    app_model_path = root / "application_models" / f"{site}.yaml"
    profile = {
        "site": site, "base_url": url,
        "login": {"mode": login_mode, "login_url": url, "liveness_url": url,
                  "logged_in_selector": None, "steps": [], "mfa": {}},
        "defaults": {"probe_url": url, "application_model": str(app_model_path)},
    }
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(yaml.safe_dump(profile, allow_unicode=True, sort_keys=False), encoding="utf-8")
    write_model(seed_model(system=system, base_url=url, roles=roles or []), app_model_path)
    intake = {
        "schema_version": 1, "system": system, "site": site, "url": url,
        "cases": str(cases_path), "roles": roles or [], "login_mode": login_mode,
        "write_policy": {"allowed": allow_write, "cleanup": cleanup},
        "status": "READY_FOR_EXPLORATION",
        "next_command": f"crosscheck ui-run --cases \"{cases_path}\" --url \"{url}\" --workspace \"{root}\"",
    }
    intake_path = root / ".crosscheck" / "intake" / f"{site}.json"
    intake_path.parent.mkdir(parents=True, exist_ok=True)
    intake_path.write_text(json.dumps(intake, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"profile": str(profile_path), "application_model": str(app_model_path),
            "intake": str(intake_path), "status": intake["status"],
            "next_command": intake["next_command"]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", default="workspace")
    parser.add_argument("--system", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--cases", required=True)
    parser.add_argument("--login-mode", choices=["manual", "credential"], default="manual")
    parser.add_argument("--role", action="append", default=[])
    parser.add_argument("--allow-write", action="store_true")
    parser.add_argument("--cleanup", default="")
    args = parser.parse_args()
    result = onboard(workspace=args.workspace, system=args.system, url=args.url, cases=args.cases,
                     login_mode=args.login_mode, roles=args.role, allow_write=args.allow_write,
                     cleanup=args.cleanup)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

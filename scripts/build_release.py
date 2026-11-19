"""Build a source ZIP from tracked files only and reject sensitive paths."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
DENIED_PARTS = {"workspace", ".auth", "artifacts", "captures", "runs", "__pycache__"}
DENIED_NAMES = {"credentials.yaml", "db.yaml", ".cleanup_registry.json", ".env"}
DENIED_SUFFIXES = {".pyc", ".key", ".pem", ".p12", ".pfx"}
FIXTURE_PREFIX = ("tests", "fixtures")
ALLOWED_ROOTS = {".agents", ".claude", ".github", "adapters", "core", "crosscheck_templates", "db", "docs", "scripts", "templates", "tests"}
ALLOWED_TOP_FILES = {
    ".gitattributes", ".gitignore", "ARCHITECTURE.md", "LICENSE", "README.md", "pyproject.toml",
    "requirements.txt", "requirements.lock", "run.py", "run_batch.py", "run_bootstrap.py",
    "run_crosscheck.py", "run_onboard.py", "run_preflight.py", "run_record.py", "run_suite.py",
    "run_tests.py", "run_verify.py", "crosscheck_cli.py",
}
REQUIRED_RELEASE_FILES = {
    "crosscheck_cli.py", "pyproject.toml", "README.md", "docs/COMPATIBILITY.md",
    "docs/TROUBLESHOOTING.md", "docs/RELEASE_CHECKLIST.md", "scripts/local_demo.py",
    "scripts/verify_distribution.py", "scripts/external_acceptance.py",
}
REQUIRED_RELEASE_RESOURCES = {
    "templates/plugin.example.py",
    "docs/COMPATIBILITY.md", "docs/TROUBLESHOOTING.md", "docs/RELEASE_CHECKLIST.md",
}
SECRET_PATTERNS = (
    b"BEGIN PRIVATE KEY", b"BEGIN RSA PRIVATE KEY", b"aws_secret_access_key",
    b"client_secret:", b"access_token:", b"refresh_token:",
)
SECRET_SCAN_EXEMPT = {"scripts/build_release.py", "tests/test_release_policy.py"}


def tracked_files(*, include_untracked: bool = False) -> list[str]:
    command = ["git", "ls-files", "--cached"]
    if include_untracked:
        command.extend(["--others", "--exclude-standard"])
    command.append("-z")
    raw = subprocess.check_output(command, cwd=ROOT)
    return [item.decode("utf-8") for item in raw.split(b"\0") if item]


def repository_state() -> dict:
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, encoding="utf-8").strip()
    status = subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=ROOT, text=True, encoding="utf-8")
    dirty = [line for line in status.splitlines() if line.strip()]
    return {"commit": commit, "dirty": dirty}


def unsafe_reason(name: str) -> str | None:
    path = PurePosixPath(name)
    parts = tuple(part.lower() for part in path.parts)
    if len(path.parts) == 1 and path.name not in ALLOWED_TOP_FILES:
        return "top-level file is not in release allowlist"
    if len(path.parts) > 1 and path.parts[0] not in ALLOWED_ROOTS:
        return "root directory is not in release allowlist"
    if parts[:2] != FIXTURE_PREFIX and set(parts) & DENIED_PARTS:
        return "sensitive/generated directory"
    if path.name.lower() in DENIED_NAMES or path.suffix.lower() in DENIED_SUFFIXES:
        return "secret or generated file"
    return None


def content_secret_reason(path: Path) -> str | None:
    try:
        relative = path.resolve().relative_to(ROOT.resolve()).as_posix()
        if relative in SECRET_SCAN_EXEMPT:
            return None
    except ValueError:
        pass
    if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webm", ".zip"}:
        return None
    data = path.read_bytes()
    lower = data.lower()
    for pattern in SECRET_PATTERNS:
        if pattern.lower() in lower:
            return f"secret pattern: {pattern.decode('ascii', errors='replace')}"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="构建不含 workspace/凭据/登录态的源码发布包")
    parser.add_argument("--out", default=str(ROOT / "dist" / "crosscheck-source.zip"))
    parser.add_argument("--allow-dirty", action="store_true", help="仅本地候选包使用;正式发布禁止")
    parser.add_argument("--include-untracked", action="store_true", help="显式包含未跟踪源码")
    args = parser.parse_args()
    state = repository_state()
    if state["dirty"] and not args.allow_dirty:
        print("ERROR: 工作树不干净,拒绝生成正式发布包。请提交/清理改动，或仅本地验证时使用 --allow-dirty。")
        return 3
    files = tracked_files(include_untracked=args.include_untracked)
    missing = sorted(REQUIRED_RELEASE_FILES - set(files))
    if missing:
        print("ERROR: 发布必需文件尚未纳入 Git 跟踪: " + ", ".join(missing))
        return 4
    missing_resources = sorted(REQUIRED_RELEASE_RESOURCES - set(files))
    if missing_resources:
        print("ERROR: 发布资源未纳入 Git 跟踪: " + ", ".join(missing_resources))
        return 5
    blocked = [(name, unsafe_reason(name)) for name in files if unsafe_reason(name)]
    blocked += [(name, reason) for name in files
                if (ROOT / name).is_file() and (reason := content_secret_reason(ROOT / name))]
    if blocked:
        for name, reason in blocked:
            print(f"ERROR: 拒绝打包 {name}: {reason}")
        return 2
    output = Path(args.out).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in files:
            source = ROOT / name
            if source.is_file():
                archive.write(source, PurePosixPath("crosscheck") / PurePosixPath(name))
        manifest = {"name": "crosscheck-agent", "commit": state["commit"],
                    "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    "dirty_build": bool(state["dirty"]), "files": sorted(files)}
        archive.writestr("crosscheck/RELEASE_MANIFEST.json",
                         json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    checksum = output.with_suffix(output.suffix + ".sha256")
    checksum.write_text(f"{digest}  {output.name}\n", encoding="ascii")
    print(f"OK: 发布包已生成: {output} ({len(files)} 个源码文件)")
    print(f"OK: SHA-256: {checksum}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

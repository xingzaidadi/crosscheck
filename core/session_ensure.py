"""
登录态自动续期:跑批前,对本批用例用到的会话逐个"检活 → 失效则按 B 模式重登"。
复用 login.ensure_session(它本就会 _check_live + 失效重登);这里只做"挑出该续哪些"。

- 只自动续 credential(B 模式)站点:无人值守能重登。
- manual(A 模式)站点失效只告警,不自动开浏览器(需人工登)。
- 按会话文件名(.auth/<site>.json 的 <site>.json)匹配 profile 与用例引用,避免路径写法差异。
"""
from __future__ import annotations

from pathlib import Path


def referenced_sessions(specs) -> set[str]:
    """本批用例引用到的会话文件名集合(主动作 + 审批步骤)。"""
    out: set[str] = set()
    for s in specs:
        if getattr(s, "session", ""):
            out.add(Path(s.session).name)
        appr = getattr(s, "approve", None) or {}
        if appr.get("session"):
            out.add(Path(appr["session"]).name)
    return out


def should_ensure(mode: str, session_file: str, referenced: set[str]) -> bool:
    """该站点是否需要自动续期:B 模式(可无人值守重登)且其会话被本批引用。"""
    return mode == "credential" and Path(session_file).name in referenced


def ensure_batch_sessions(specs, *, ensure_fn=None) -> list[dict]:
    """跑批前确保会话新鲜。返回每个站点的动作 [{site, action}]:
    ensured(B 模式已检活/续期)/ skip-manual(A 模式失效需人工)/ 失败则 action=error。"""
    from core.login import ensure_session
    from core.profile import load_profile, list_profiles
    from core.config import site_credentials

    ensure_fn = ensure_fn or ensure_session
    referenced = referenced_sessions(specs)
    done: list[dict] = []
    for name in list_profiles():
        try:
            prof = load_profile(name)
        except Exception:  # noqa: BLE001
            continue
        if Path(prof.session_file).name not in referenced:
            continue
        if prof.login.mode != "credential":
            done.append({"site": prof.site, "action": "skip-manual"})
            continue
        try:
            ensure_fn(prof, site_credentials(prof.site))
            done.append({"site": prof.site, "action": "ensured"})
        except Exception as e:  # noqa: BLE001
            done.append({"site": prof.site, "action": "error", "error": str(e)[:120]})
    return done

"""
登录态获取。两种模式(由 profile 的 login.mode 决定):

  A  manual     —— 开有头浏览器,人工登一次(含 2FA/验证码/SSO/两段式),回车后保存 storageState。
                   换账号 = 换 session 文件;最省心,能过一切登录墙(含企业 SSO/两段式)。
  B  credential —— 声明式自动登录:按 login.steps 填账密、点登录,保存 storageState。
                   只适合简单账密页。账密从 config/credentials.yaml 的 sites.<site> 取。

无论哪种,结果都是一份 .auth/<site>.json;之后 probe/回放复用它,失效才重登。
存活性校验:打开 liveness_url,看 logged_in_selector 是否在、或是否被打回 /login。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from core.profile import Profile


class LoginError(RuntimeError):
    pass


def _run_steps(page: Any, steps: list[dict], creds: dict | None, shot=None) -> None:
    """
    跑声明式步骤:登录(B 模式)和检索操作共用同一套。
    page 只需支持 goto/fill/click/press/select_option/wait_*,故可脱离浏览器单测。
    shot(name): 可选截图回调,遇到 {screenshot: 名} 步骤时调用。
    """
    creds = creds or {}
    for step in steps:
        if not isinstance(step, dict) or len(step) != 1:
            raise LoginError(f"每个步骤必须是单键字典,如 {{fill: {{...}}}};得到: {step!r}")
        action, spec = next(iter(step.items()))
        if action == "goto":
            page.goto(spec["url"], wait_until="domcontentloaded")
        elif action == "fill":
            val = spec.get("value")
            if val is None and "value_from" in spec:
                key = spec["value_from"]
                if key not in creds or creds[key] in (None, ""):
                    raise LoginError(
                        f"凭据缺少 {key!r}:mode=credential 需在 config/credentials.yaml 的 "
                        f"sites.<site> 下配 {key}")
                val = creds[key]
            if val is None:
                raise LoginError(f"fill 步骤缺少 value / value_from: {spec!r}")
            page.fill(spec["selector"], str(val))
        elif action == "click":
            page.click(spec["selector"], timeout=spec.get("timeout", 10000))
        elif action == "select":  # 原生 <select> 下拉;自定义下拉用 click 序列
            page.select_option(spec["selector"],
                               label=spec.get("label"), value=spec.get("value"))
        elif action == "press":
            page.press(spec["selector"], spec["key"])
        elif action == "wait_for":
            page.wait_for_selector(spec["selector"], timeout=spec.get("timeout", 15000))
        elif action == "wait_ms":
            ms = spec.get("ms", 1000) if isinstance(spec, dict) else spec
            page.wait_for_timeout(int(ms))
        elif action == "screenshot":
            name = spec if isinstance(spec, str) else spec.get("name", "step")
            if shot:
                shot(name)
        else:
            raise LoginError(
                f"未知步骤: {action!r}"
                "(支持 goto/fill/click/select/press/wait_for/wait_ms/screenshot)")


def _page_logged_in(page, cfg) -> bool:
    """当前 page 是否处于已登录:有 logged_in_selector 看它在不在,否则看是否被打回 /login。"""
    if cfg.logged_in_selector:
        return page.locator(cfg.logged_in_selector).count() > 0
    return "/login" not in page.url.lower()


def _check_live(profile: Profile, session_file: str) -> bool:
    """用保存的登录态打开 liveness_url,判断是否仍登录。"""
    from playwright.sync_api import sync_playwright

    cfg = profile.login
    url = cfg.liveness_url or profile.base_url
    if not url:
        return True  # 没给判活地址,无法校验,乐观放行(probe 阶段抓不到再暴露)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(storage_state=session_file)
        page = ctx.new_page()
        live = False
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(1500)
            live = _page_logged_in(page, cfg)
        except Exception:  # noqa: BLE001
            live = False
        finally:
            ctx.close()
            browser.close()
    return live


def _manual_login(profile: Profile, session_file: str, poll_seconds: int = 240) -> None:
    """
    A 模式:开有头浏览器,人工登一次。
      - 交互式终端(TTY):等你按回车。
      - 非 TTY(经 Bash 工具跑,拿不到你的键入):浏览器弹出你登,我轮询登录状态直到成功/超时。
    """
    import sys as _sys
    from playwright.sync_api import sync_playwright

    cfg = profile.login
    Path(session_file).parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(cfg.login_url or profile.base_url, wait_until="domcontentloaded")
        print(f"【手动登录 · {profile.site}】浏览器已打开: {cfg.login_url or profile.base_url}")
        print("  请在浏览器里完成登录(含 2FA/验证码/SSO/两段式)。")

        if _sys.stdin and _sys.stdin.isatty():
            print("  完成后回到终端按回车…")
            try:
                input()
            except EOFError:
                page.wait_for_timeout(poll_seconds * 1000)
        else:
            print(f"  我在 {poll_seconds}s 内轮询登录状态,登录成功即自动保存…")
            import time
            deadline = time.time() + poll_seconds
            ok = False
            while time.time() < deadline:
                page.wait_for_timeout(3000)
                try:
                    if _page_logged_in(page, cfg):
                        ok = True
                        break
                except Exception:  # noqa: BLE001
                    pass
            print("  检测到已登录。" if ok else "  ⚠ 轮询超时,仍按当前状态保存(可能未登录)。")

        page.wait_for_timeout(500)
        ctx.storage_state(path=session_file)
        ctx.close()
        browser.close()
    print(f"  ✓ 登录态已保存 → {session_file}")


def _credential_login(profile: Profile, creds: dict | None, session_file: str,
                      headless: bool = False) -> None:
    from playwright.sync_api import sync_playwright

    cfg = profile.login
    if not cfg.steps:
        raise LoginError("mode=credential 但 profile 未配置 login.steps")
    Path(session_file).parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(cfg.login_url or profile.base_url, wait_until="domcontentloaded")
        _run_steps(page, cfg.steps, creds)
        page.wait_for_timeout(2000)
        ctx.storage_state(path=session_file)
        ctx.close()
        browser.close()
    print(f"  ✓ 自动登录完成,登录态已保存 → {session_file}")


def ensure_session(profile: Profile, creds: dict | None = None, *,
                   force: bool = False, check: bool = True,
                   session_file: str | None = None) -> str:
    """
    确保有可用登录态,返回 session 文件路径。
      - 已有且存活 → 直接复用;
      - force 或已失效 → 按 mode 重登(A 人工 / B 声明式);
    session_file 可指定(多角色:每角色一份登录态);默认用 profile.session_file。
    """
    session_file = session_file or profile.session_file
    if not force and Path(session_file).exists():
        if not check or _check_live(profile, session_file):
            print(f"  复用已有登录态: {session_file}")
            return session_file
        print("  已有登录态已失效,重新登录。")

    mode = profile.login.mode
    if mode == "manual":
        _manual_login(profile, session_file)
    elif mode == "credential":
        _credential_login(profile, creds, session_file)
    else:
        raise LoginError(f"未知 login.mode: {mode!r}(支持 manual / credential)")

    if check and not _check_live(profile, session_file):
        raise LoginError("登录后存活性校验未通过:确认 login_url / liveness_url / "
                         "logged_in_selector 是否正确。")
    return session_file

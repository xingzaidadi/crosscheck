"""Login-page detection and one-time human handoff for profile-free runs."""
from __future__ import annotations

import time


LOGIN_TERMS = ("登录", "登陆", "sign in", "log in", "验证码", "verification code", "password")


def looks_like_login(page) -> bool:
    try:
        url = str(page.url or "").lower()
        body = page.locator("body").inner_text(timeout=2000)[:8000].lower()
        password_count = page.locator('input[type="password"]').count()
    except Exception:
        return False
    return password_count > 0 or any(term in url for term in ("/login", "/signin", "/auth")) \
        or sum(term in body for term in LOGIN_TERMS) >= 2


def wait_for_human_login(page, *, timeout_seconds: int = 240) -> bool:
    """Wait until the current page no longer looks like a login page."""
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if not looks_like_login(page):
            return True
        page.wait_for_timeout(2000)
    return False

"""
前端校验断言(通用):验页面在非法输入后给出了预期校验报错。
很多"非法值被拦截"的校验在前端(日期控件禁选过去、必填红字提示…),后端信任前端、不复查,
这类在 API 层测会误报"应拒却成功"。正确做法:走 UI,填非法值 → 读页面校验报错 → 断言含预期提示。
配合 prober 读到的校验报错文本用(prober 复用 discovery.fields.read_validation_errors)。
"""
from __future__ import annotations


def check_validation(errors: list[str], expect: list[str]) -> tuple[bool, dict]:
    """断言每条预期提示子串都在页面校验报错里出现。errors=页面实际报错文本列表。"""
    joined = " ｜ ".join(errors or [])
    cols, rows, ok_all = ["预期含提示", "命中", "一致"], [], True
    for e in expect:
        hit = e in joined
        ok_all = ok_all and hit
        rows.append([e, "是" if hit else "否", "✓" if hit else "✗"])
    return ok_all, {"name": "前端校验报错", "ok": ok_all,
                    "expected": "非法输入后页面给出预期校验提示",
                    "actual": f"页面报错:{joined[:160] or '(无)'}", "cols": cols, "rows": rows}

"""data_prep 新能力 回归(离线、零环境):db_wait 轮询到状态翻转、db_capture 查库抓标量入 vars、
http 步骤独立 session、整值占位 {{var}} 保留原类型。用假 db/adapter 注入,毫秒级。
跑:python tests/test_data_prep_db.py
"""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.engine import _run_prep_step  # noqa: E402
from adapters.api_adapter import ApiAdapter  # noqa: E402


class FakeDB:
    """按 (table) 返回预设标量;status 轮询第 N 次才翻转,模拟异步。"""
    def __init__(self):
        self.calls = 0
    def query(self, sql, params=None):
        if "FROM demand_request " in sql or "FROM demand_request\n" in sql or "demand_request WHERE" in sql:
            if "request_status" in sql:
                self.calls += 1
                return [{"v": "TO_ACCEPT" if self.calls >= 2 else "PENDING_APPROVE"}]
            if "version" in sql:
                return [{"v": 7}]
        if "demand_request_item" in sql:
            return [{"v": 593}]
        return [{"v": None}]


class FakeAdapter:
    def __init__(self):
        self.seen = []
    def call(self, prep, vars):
        self.seen.append((prep.get("url"), dict(vars)))
        return SimpleNamespace(ok=True, api_body={"data": {"demandRequestCode": "REQX"}}, error=None, api_status=200)


def main():
    print("data_prep 新能力 回归:\n")

    # 1) db_wait:状态第2次轮询才翻到 TO_ACCEPT,应等到并通过(interval 极小)
    db = FakeDB()
    vars = {"marker": "AUTOTEST_X", "code": "REQX"}
    step = {"db_wait": {"table": "demand_request", "column": "request_status",
                        "where": "demand_request_code='{{code}}'", "equals": "TO_ACCEPT",
                        "timeout_s": 2, "interval_s": 0.01}}
    did, env = _run_prep_step(step, FakeAdapter(), db, vars)
    assert not env, f"db_wait 应成功无报错: {env}"
    assert db.calls >= 2, "应轮询到状态翻转"
    print("    ✓ db_wait 轮询到状态翻转(PENDING_APPROVE→TO_ACCEPT)")

    # 2) db_capture:从库抓 ver/itemId 入 vars
    step2 = {"db_capture": {
        "ver": {"table": "demand_request", "column": "version", "where": "demand_request_code='{{code}}'"},
        "itemId": {"table": "demand_request_item", "column": "id", "where": "demand_request_code='{{code}}'"}}}
    _run_prep_step(step2, FakeAdapter(), db, vars)
    assert vars["ver"] == 7 and vars["itemId"] == 593, vars
    print(f"    ✓ db_capture 查库抓标量入 vars:ver={vars['ver']} itemId={vars['itemId']}")

    # 3) http 步骤 + capture
    fa = FakeAdapter()
    step3 = {"method": "POST", "url": "/demand/api/x", "body": {"a": 1}, "capture": {"code2": "data.demandRequestCode"}}
    _run_prep_step(step3, fa, db, vars)
    assert vars["code2"] == "REQX" and fa.seen[0][0] == "/demand/api/x", (vars, fa.seen)
    print("    ✓ http 步骤发请求 + capture 抓返回值入 vars")

    # 4) 整值占位保留原类型:{{ver}} 是 int 7,不被字符串化;混在串里仍替换
    rendered = ApiAdapter._render({"version": "{{ver}}", "note": "v={{ver}}", "itemId": "{{itemId}}"}, vars)
    assert rendered["version"] == 7 and isinstance(rendered["version"], int), rendered
    assert rendered["itemId"] == 593 and isinstance(rendered["itemId"], int), rendered
    assert rendered["note"] == "v=7", rendered
    print("    ✓ 整值占位 {{ver}} 保留 int 类型;混串占位仍按字符串替换")

    print("\n全部通过 ✅  —— 多步流水线(等状态→查库拿键→动作)+ 类型保真 已回归锁定")


if __name__ == "__main__":
    main()

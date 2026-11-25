"""core.xlayer_contract 真执行回归(main()+assert)。

用真实 crosscheck 自驱对账抓到的数据喂检查器,把跨层契约发现固化成可复现回归:
- dangling_enum: 前端"待测算"请求 [WAITING_ESTIMATION,REJECTED,REVOKED]，后端字典仅
  {WAITING_ESTIMATION,COMPLETED,NON_ESTIMATION,SYNC_FAILED} → REJECTED/REVOKED 悬空。
- default_filter_leak: 无过滤裸调返回四态，"待测算"标签声明仅 WAITING_ESTIMATION → 泄漏。
- pagination_invariants: p2p 子系统 /api/mi/cp/list/project，total=25564，
  pageSize 10→pages2557/返回10，pageSize50→pages512/返回50，不变量全成立。
全程零业务:检查器只吃抽象 请求/响应/枚举 结构，不含任何采购业务词。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.xlayer_contract import (
    check_dangling_enum,
    check_default_filter_leak,
    check_error_status_contract,
    check_pagination_invariants,
    run_contract_checks,
)


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    BACKEND_DICT = ["WAITING_ESTIMATION", "COMPLETED", "NON_ESTIMATION", "SYNC_FAILED"]

    # 1) 悬空枚举:真实"待测算"请求三态，后端字典不含 REJECTED/REVOKED。
    f = check_dangling_enum(["WAITING_ESTIMATION", "REJECTED", "REVOKED"], BACKEND_DICT)
    vals = {x.evidence["value"] for x in f}
    _assert(vals == {"REJECTED", "REVOKED"}, f"应检出两个悬空枚举, got {vals}")
    _assert(all(x.severity == "contract-risk" for x in f), "悬空枚举是 contract-risk")
    print("[1] dangling_enum 检出 REJECTED/REVOKED ✓")

    # 2) 字典齐全时无悬空。
    f2 = check_dangling_enum(["WAITING_ESTIMATION", "COMPLETED"], BACKEND_DICT)
    _assert(f2 == [], "全部已知枚举不应报")
    print("[2] 已知枚举不误报 ✓")

    # 3) 默认过滤泄漏:无过滤返回四态，"待测算"声明仅 WAITING_ESTIMATION。
    f3 = check_default_filter_leak(BACKEND_DICT, ["WAITING_ESTIMATION"])
    _assert(len(f3) == 1, "一条泄漏发现")
    leaked = set(f3[0].evidence["leaked_values"])
    _assert(leaked == {"COMPLETED", "NON_ESTIMATION", "SYNC_FAILED"}, f"泄漏三态, got {leaked}")
    print("[3] default_filter_leak 检出越界三态 ✓")

    # 4) scope 覆盖全集时无泄漏("全部"标签)。
    f4 = check_default_filter_leak(BACKEND_DICT, BACKEND_DICT)
    _assert(f4 == [], "全集 scope 不泄漏")
    print("[4] 全集 scope 不误报 ✓")

    # 5) 分页不变量成立(p2p 真实:total 25564 两档一致,pages/返回数自洽)。
    good = [
        {"pageSize": 10, "pageNum": 1, "total": 25564, "pages": 2557, "returned": 10},
        {"pageSize": 50, "pageNum": 1, "total": 25564, "pages": 512, "returned": 50},
    ]
    _assert(check_pagination_invariants(good) == [], "真实分页不变量应全成立")
    print("[5] pagination 不变量成立(真实 p2p 数据) ✓")

    # 6) 分页违例:total 漂移 + pages 错 + 末页返回数错。
    bad = [
        {"pageSize": 10, "pageNum": 1, "total": 100, "pages": 10, "returned": 10},
        {"pageSize": 10, "pageNum": 1, "total": 99, "pages": 9, "returned": 10},  # total 变+pages 错(应10)
    ]
    checks = {c.check for c in check_pagination_invariants(bad)}
    _assert("pagination_total_unstable" in checks, "应检出 total 漂移")
    _assert("pagination_pages_wrong" in checks, "应检出 pages 错")
    # 末页返回数:total=45,pageSize=20,pageNum=3 → 期望 5
    lastpage = check_pagination_invariants([{"pageSize": 20, "pageNum": 3, "total": 45, "returned": 10}])
    _assert(any(c.check == "pagination_rows_wrong" for c in lastpage), "末页返回数错应检出")
    print("[6] pagination 违例检出(total/pages/rows) ✓")

    # 7) run_contract_checks 聚合 + 软门(只报不判)。
    agg = run_contract_checks({
        "dangling_enum": {"requested": ["WAITING_ESTIMATION", "REJECTED"], "dictionary": BACKEND_DICT},
        "default_filter_leak": {"unfiltered": BACKEND_DICT, "scope": ["WAITING_ESTIMATION"]},
        "pagination": good,
    })
    _assert(agg["consistent"] is False, "有发现则不一致")
    _assert(agg["finding_count"] == 1 + 1, "1 悬空 + 1 泄漏(分页无违例)")
    _assert(set(agg.keys()) == {"consistent", "finding_count", "findings"}, "只返回报告,不含判决副作用")
    print("[7] run_contract_checks 聚合+软门 ✓")

    # 8) 全绿 spec:一致。
    clean = run_contract_checks({
        "dangling_enum": {"requested": ["COMPLETED"], "dictionary": BACKEND_DICT},
        "pagination": good,
    })
    _assert(clean["consistent"] is True and clean["finding_count"] == 0, "干净 spec 应一致")
    print("[8] 干净 spec 判一致 ✓")

    # 9) 错误响应状态码契约(真实只读探测 /demand/api/* 7 端点所得):
    #    approve 失败却回 HTTP 200(掩盖错误);5 个缺参端点回 500(客户端错当服务端错);
    #    accept/batch/validate 是正范式(参数校验 → 400)。
    err_samples = [
        {"id": "approve", "http_status": 200, "success": False, "param_error": True},
        {"id": "item/close", "http_status": 500, "success": False, "param_error": True},
        {"id": "demand/close", "http_status": 500, "success": False, "param_error": True},
        {"id": "accept/return", "http_status": 500, "success": False, "param_error": True},
        {"id": "template/save", "http_status": 500, "success": False, "param_error": True},
        {"id": "batchGetFdsPreSignedUrl", "http_status": 500, "success": False, "param_error": True},
        {"id": "batch/validate", "http_status": 400, "success": False, "param_error": True},  # 正范式,不报
    ]
    f9 = check_error_status_contract(err_samples)
    checks9 = [c.check for c in f9]
    _assert("error_masked_as_success" in checks9, "approve 2xx 掩盖错误应检出")
    _assert(checks9.count("client_error_as_server") == 5, f"5 个 5xx 客户端错应检出, got {checks9.count('client_error_as_server')}")
    # batch/validate(400)是正范式,不应在任何发现里出现
    _assert(all("batch/validate" not in c.detail for c in f9), "400 正范式不应报")
    # 成功样本不检视
    _assert(check_error_status_contract([{"id": "ok", "http_status": 200, "success": True}]) == [], "成功调用不报")
    print("[9] error_status 契约检出(200掩盖错误/5xx客户端错)✓")

    # 10) run_contract_checks 接入 error_status。
    agg2 = run_contract_checks({"error_status": err_samples})
    _assert(agg2["finding_count"] == 1 + 5, "1 掩盖 + 5 客户端错当服务端错")
    _assert(agg2["consistent"] is False, "有发现则不一致")
    print("[10] run_contract_checks 接入 error_status ✓")

    print("\nALL PASS · core.xlayer_contract 跨层契约(悬空枚举/默认过滤泄漏/分页不变量/错误状态码契约/聚合软门)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

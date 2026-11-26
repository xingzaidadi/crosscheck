"""契约候选路由分配器验证(离线、零业务):验『契约端点 → 用例候选路由 → readiness 翻正』闭环。
跑:python tests/test_route_assign.py
"""
from __future__ import annotations

import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.readiness import Capabilities, case_endpoints, compute_one, norm_endpoint  # noqa: E402
from core.route_assign import (  # noqa: E402
    CONTRACT_MARKER, assign_routes, endpoint_signals, stamp_contract_note, tokens,
)


class _Case:
    def __init__(self, cid, text):
        self.case_id = cid
        self.name = text
        self.steps_text = text
        self.expected_text = ""
        self.preconditions = ""
        self.notes = ""


_EPS = [
    {"http": "POST", "path": "/api/items", "method_name": "createItem",
     "request_dto": "CreateItemReq", "fields": [{"name": "title", "type": "string", "required": True}]},
    {"http": "GET", "path": "/api/items/search", "method_name": "searchItems",
     "request_dto": "", "fields": []},
    {"http": "POST", "path": "/api/orders", "method_name": "createOrder",
     "request_dto": "CreateOrderReq", "fields": [{"name": "itemId", "type": "integer", "required": True}]},
]


def main():
    print("契约候选路由分配器验证:\n")

    # 0) 分词:驼峰拆分 + 复数归一(零业务)
    t = tokens("createItemRequest")
    assert {"create", "item"} <= t, t
    assert "item" in tokens("items"), "复数应归一到单数"
    print("    ✓ tokens:驼峰拆分 createItem→{create,item},复数 items→item 归一")

    # 1) 翻正闭环:unknown 用例 → 候选 → compute_one 从 False 翻 True
    case = _Case("TC_CREATE", "create a new item with title")
    # 先证明它裸判 unknown(散文无 /api 路径、无路由)
    r0 = compute_one(case.case_id, "create a new item with title", None, Capabilities())
    assert r0.ready is False and "unknown" in r0.note, r0.note

    cands = assign_routes([case], _EPS)
    assert len(cands) == 1, [c.endpoint for c in cands]
    cand = cands[0]
    assert cand.endpoint == "POST /api/items", cand.endpoint
    # 把候选路由塞进 by_case_id,caps.reachable 含该端点 → 翻 true
    caps = Capabilities(reachable={norm_endpoint("/api/items")}, catalog={norm_endpoint("/api/items")})
    r1 = compute_one(case.case_id, "create a new item with title", cand.route, caps)
    assert r1.ready is True, (r1.ready, r1.note)
    # 候选 route 确实被 case_endpoints 识别出端点
    assert norm_endpoint("/api/items") in case_endpoints(case.case_id, "", cand.route)
    print(f"    ✓ 翻正闭环:unknown 用例经候选路由 {cand.endpoint} → ready False→True(score={cand.score})")

    # 2) 宁缺毋滥:无端点词 / 歧义(分差<margin)都不配
    c_noise = assign_routes([_Case("TC_NOISE", "open the page and look around")], _EPS)
    assert c_noise == [], c_noise
    c_ambig = assign_routes([_Case("TC_AMBIG", "do something with item")], _EPS)
    assert c_ambig == [], "歧义用例(多端点势均力敌)应被双门槛拦截"
    print("    ✓ 宁缺毋滥:无端点词用例、歧义用例都不产候选(不制造假 ready)")

    # 3) contract 标记:stamp 后 note 含 contract,且与 scorecard zero_route 口径一致
    stamped = stamp_contract_note(r1, cand)
    assert CONTRACT_MARKER in stamped.note.lower(), stamped.note
    # 复刻 scripts/scorecard.py:_read_readiness 的 zero_route 判断
    zero_route_hit = stamped.ready and "contract" in str(stamped.note).lower()
    assert zero_route_hit, "翻正用例应被 scorecard 计入 zero_route"
    print("    ✓ contract 标记:stamp 后 note 带 contract,scorecard 口径计入 zero_route")

    # 4) 确定性:同输入同输出
    a = assign_routes([case], _EPS)
    b = assign_routes([case], _EPS)
    assert [x.to_dict() for x in a] == [x.to_dict() for x in b], "分配必须确定性"
    print("    ✓ 确定性:同输入两次分配结果完全一致")

    # 5) 多用例可翻正统计(端到端口径预演):只有无歧义的写用例被翻正
    #    TC01 create item → 配;TC02 search 是只读 GET(route_draft 不产写路由)→ 不配;
    #    TC03 "order for an item" 同时命中 orders/items 同分 → 歧义拦截;TC04/05 无端点词/歧义 → 不配。
    cases = [_Case("TC01", "create a new item"), _Case("TC02", "search items by keyword"),
             _Case("TC03", "create an order for an item"), _Case("TC04", "open the page"),
             _Case("TC05", "do something with item")]
    got = assign_routes(cases, _EPS)
    ids = {c.case_id for c in got}
    assert "TC01" in ids, ids                          # 明确写用例翻正
    assert ids == {"TC01"}, f"只有无歧义写用例应被翻正,实得 {ids}"
    print(f"    ✓ 5 条用例 → {len(got)} 条可翻正({sorted(ids)});只读/歧义/无关用例一律不配(宁缺毋滥)")

    # 6) 可达性扣除:投影翻正只认"端点确知可达"的,未证可达的进 unproven(不虚高、不灌数)
    _coverage_reachability_gate()

    print("\n全部通过 ✅  —— 契约→候选路由→readiness 翻正闭环打通,候选态、宁缺毋滥、零业务")


def _coverage_reachability_gate():
    """route_assign._coverage_report 的 flips 必须扣掉"端点未证可达"的候选。

    构造:TC_HIT 候选端点已被某 ready 用例占用(确知可达)→可翻正;
          TC_MISS 候选端点谁都没用过(未证可达)→不计 flips、进 unproven。
    """
    import tempfile
    from pathlib import Path
    import yaml
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
    from route_assign import _coverage_report  # noqa

    eps = [
        {"http": "POST", "path": "/api/items", "method_name": "createItem",
         "request_dto": "CreateItemReq", "fields": [{"name": "title", "required": True}]},
        {"http": "POST", "path": "/api/orders", "method_name": "createOrder",
         "request_dto": "CreateOrderReq", "fields": [{"name": "itemId", "required": True}]},
    ]
    hit = _Case("TC_HIT", "create a new item")        # → /api/items
    miss = _Case("TC_MISS", "create an order")        # → /api/orders
    cands = assign_routes([hit, miss], eps)
    assert {c.case_id for c in cands} == {"TC_HIT", "TC_MISS"}, [c.case_id for c in cands]

    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        (ws / "config").mkdir(parents=True)
        # 一条已 ready 的用例占用 /api/items(=确知可达);/api/orders 无人占用(未证可达)
        yaml.safe_dump({"by_case_id": {
            "TC_READY": {"write": {"request": {"method": "POST", "url": "/api/items"}}}}},
            open(ws / "config" / "case_routes.yaml", "w", encoding="utf-8"), allow_unicode=True)
        yaml.safe_dump({
            "TC_READY": {"ready": True, "blocked_by": [], "note": "ok"},
            "TC_HIT": {"ready": False, "blocked_by": [], "note": "unknown"},
            "TC_MISS": {"ready": False, "blocked_by": [], "note": "unknown"},
        }, open(ws / "readiness.yaml", "w", encoding="utf-8"), allow_unicode=True)

        rep = _coverage_report([hit, miss], cands, str(ws))
        bl = rep["baseline"]
        # /api/items 确知可达 → TC_HIT 可翻正;/api/orders 未证 → TC_MISS 进 unproven
        assert bl["flips"] == 1, bl
        assert bl["flips_reachable"] == ["TC_HIT"], bl["flips_reachable"]
        assert bl["unproven_need_probe"] == ["TC_MISS"], bl["unproven_need_probe"]
    print("    ✓ 可达性扣除:候选端点确知可达才计 flips,未证可达进 unproven(不虚高/不灌数)")


if __name__ == "__main__":
    main()

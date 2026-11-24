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

    print("\n全部通过 ✅  —— 契约→候选路由→readiness 翻正闭环打通,候选态、宁缺毋滥、零业务")


if __name__ == "__main__":
    main()

"""core/route_draft.py 离线测试:中性契约 → 路由骨架,零业务。"""
import sys
from pathlib import Path
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.route_draft import endpoint_to_route, drafts_from_contracts


def main():
    contracts = [
        {"http": "POST", "path": "/shop/api/order/close", "request_dto": "OrderOpRequest",
         "fields": [{"name": "orderCode", "type": "String", "required": True},
                    {"name": "version", "type": "Integer", "required": True},
                    {"name": "remark", "type": "String", "required": False}]},
        {"http": "GET", "path": "/shop/api/order/detail/{id}", "request_dto": None, "fields": []},
        {"http": "POST", "path": "/shop/api/order/page", "request_dto": "PageReq", "fields": []},
    ]
    # 写端点出骨架;只读/分页不出
    r = endpoint_to_route(contracts[0], "/shop")
    assert r["mode"] == "write" and r["write"]["request"]["url"] == "/api/order/close", r
    assert r["write"]["request"]["body"]["orderCode"] == "" or "orderCode" in r["write"]["request"]["body"]
    assert r["write"]["request"]["body"]["version"] == "{{ver}}", r["write"]["request"]["body"]
    assert r["write"]["_contract"]["required"] == ["orderCode", "version"]
    print("    ✓ 写端点出骨架:body 按 DTO 铺、version→{{ver}}、必填项标注")

    assert endpoint_to_route(contracts[1]) is None, "GET 不出写路由"
    assert endpoint_to_route(contracts[2]) is None, "/page 只读不出写路由"
    print("    ✓ 只读/分页端点不出写路由草稿")

    drafts = drafts_from_contracts(contracts, "/shop")
    assert set(drafts) == {"/shop/api/order/close"}, set(drafts)
    print(f"    ✓ 批量草拟:只出写端点 {list(drafts)}")
    print("\n契约→路由自动草拟 通过 ✅")


if __name__ == "__main__":
    main()

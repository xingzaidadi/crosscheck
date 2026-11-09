"""源码契约自发现 验证(离线、零业务):用中性 shop/order 源码片段,验端点抽取 + DTO 字段/校验解析。
跑:python tests/test_srcmap.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.discovery.srcmap import parse_controller, parse_dto_fields, build_contracts, norm_path  # noqa: E402

CTRL = '''
@RestController
@RequestMapping("/api/orders")
public class OrderController {
    @PostMapping("/close")
    public Response<OrderResult> close(@Valid @RequestBody OrderOpRequest request) { ... }

    @PostMapping("/item/close")
    public Response<OrderResult> itemClose(@Valid @RequestBody OrderItemCloseRequest request) { ... }

    @GetMapping("/detail/{code}")
    public Response<OrderDetail> detail(@PathVariable String code) { ... }
}
'''

DTO_OP = '''
public class OrderOpRequest {
    @NotBlank(message = "code 不能为空")
    private String orderCode;
    private String remark;
    @NotNull(message = "version 不能为空")
    private Integer version;
}
'''

DTO_ITEM = '''
public class OrderItemCloseRequest {
    @NotBlank private String orderCode;
    @NotNull  private Long itemId;
    @Size(max = 100) private String reason;
}
'''


def main():
    print("源码契约自发现 验证:\n")

    # 1) norm_path 规整
    assert norm_path("shop", "/api/orders", "/close") == "/shop/api/orders/close"
    print("    ✓ norm_path 拼接规整(去空段/单斜杠)")

    # 2) parse_controller:端点 + 请求 DTO + HTTP
    eps = parse_controller(CTRL, "shop")
    byp = {e["path"]: e for e in eps}
    assert "/shop/api/orders/close" in byp and byp["/shop/api/orders/close"]["request_dto"] == "OrderOpRequest"
    assert byp["/shop/api/orders/item/close"]["request_dto"] == "OrderItemCloseRequest"
    assert byp["/shop/api/orders/detail/{code}"]["http"] == "GET"
    print(f"    ✓ parse_controller:{len(eps)} 端点,路径=上下文+类前缀+方法,@RequestBody→DTO")

    # 3) parse_dto_fields:字段 + 必填 + 规则
    f = {x["name"]: x for x in parse_dto_fields(DTO_OP)}
    assert f["orderCode"]["required"] and not f["remark"]["required"] and f["version"]["required"]
    fi = {x["name"]: x for x in parse_dto_fields(DTO_ITEM)}
    assert any(r["ann"] == "Size" for r in fi["reason"]["rules"]), fi["reason"]
    print("    ✓ parse_dto_fields:必填(@NotBlank/@NotNull)+ 规则(@Size)识别正确")

    # 4) build_contracts:走目录(临时中性源码),端点契约带字段
    with tempfile.TemporaryDirectory() as d:
        root = Path(d) / "src" / "model" / "req"
        root.mkdir(parents=True)
        (Path(d) / "OrderController.java").write_text(CTRL, encoding="utf-8")
        (root / "OrderOpRequest.java").write_text(DTO_OP, encoding="utf-8")
        (root / "OrderItemCloseRequest.java").write_text(DTO_ITEM, encoding="utf-8")
        cons = build_contracts(d, "shop")
    byp = {c["path"]: c for c in cons}
    close = byp["/shop/api/orders/close"]
    assert close["request_dto"] == "OrderOpRequest" and len(close["fields"]) == 3
    assert sum(1 for x in close["fields"] if x["required"]) == 2
    print(f"    ✓ build_contracts 走目录:{len(cons)} 端点,契约带 DTO 字段/必填")

    print("\n全部通过 ✅  —— 从源码读接口契约(端点/DTO/校验规则),零业务、离线可测")


if __name__ == "__main__":
    main()

"""契约摄取 验证(离线、零业务):用中性 OpenAPI 文档验 provider 注册、canonical 规范化、
契约→ExecSpec 草稿 + 负例派生。
跑:python tests/test_contract_ingest.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import contract_ingest as ci  # noqa: E402
from core.contract_ingest.to_execspec import contract_to_drafts  # noqa: E402

# 中性 OpenAPI 3 文档:一个列表检索接口 + 一个创建接口(带校验),无任何业务词
_SPEC = {
    "openapi": "3.0.0",
    "paths": {
        "/api/items/search": {
            "post": {
                "operationId": "searchItems",
                "requestBody": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/SearchReq"}}}},
            }
        },
        "/api/items": {
            "post": {
                "operationId": "createItem",
                "requestBody": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/CreateReq"}}}},
            }
        },
    },
    "components": {"schemas": {
        "SearchReq": {"type": "object", "properties": {"keyword": {"type": "string"}}},
        "CreateReq": {
            "type": "object",
            "required": ["name"],
            "properties": {
                "name": {"type": "string", "maxLength": 10},
                "amount": {"type": "integer", "maximum": 100, "minimum": 1},
            },
        },
    }},
}


def main():
    print("契约摄取 验证:\n")

    assert "java_spring" in ci.providers() and "openapi" in ci.providers()
    print("    ✓ provider 注册表含 java_spring + openapi")

    with tempfile.TemporaryDirectory() as d:
        spec_path = Path(d) / "neutral.json"
        spec_path.write_text(json.dumps(_SPEC), encoding="utf-8")
        contract = ci.ingest("openapi", str(spec_path), site="neutral")

    assert contract.source == "openapi"
    assert len(contract.endpoints) == 2
    eps = {f"{e.http} {e.path}": e for e in contract.endpoints}
    assert "POST /api/items" in eps and "POST /api/items/search" in eps
    print("    ✓ OpenAPI → canonical:2 个端点,路径/方法正确")

    create = eps["POST /api/items"]
    name_field = next(f for f in create.fields if f.name == "name")
    assert name_field.required is True
    assert any(r["ann"] == "Size" and "max=10" in r["arg"] for r in name_field.rules), name_field.rules
    amount_field = next(f for f in create.fields if f.name == "amount")
    assert any(r["ann"] == "Max" for r in amount_field.rules)
    assert any(r["ann"] == "Min" for r in amount_field.rules)
    print("    ✓ required / maxLength→Size / maximum→Max / minimum→Min 规则同构 Java 注解")

    drafts = contract_to_drafts(contract)
    assert drafts["endpoint_count"] == 2
    # 负例:name 缺失(required)、name 超长(Size)、amount 越上界(Max)、amount 越下界(Min) = 4
    assert drafts["negative_count"] >= 4, drafts["negative_count"]
    create_specs = next(s for s in drafts["specs"] if s["endpoint"] == "POST /api/items")
    # 必填 name 在 OpenAPI required 下应派生"缺字段"负例(规则记为 NotNull)
    missing = [n for n in create_specs["negatives"] if n["rule"] in ("NotBlank", "NotNull", "NotEmpty")]
    assert any(n["field"] == "name" for n in missing), "required 字段应有缺失型负例"
    size_neg = next(n for n in create_specs["negatives"] if n["rule"] == "Size")
    assert len(str(size_neg["request"]["body"]["name"])) == 11, "超长应为 max+1"
    assert size_neg["assertions"]["response"]["status_gte"] == 400
    assert size_neg["verify_status"] == "draft"
    print("    ✓ 契约→负例草稿:required 缺失 + 超长=max+1、期望 4xx、verify_status=draft")

    happy = create_specs["happy"]
    assert happy["request"]["method"] == "POST"
    assert happy["request"]["url"] == "/api/items"
    assert "name" in happy["request"]["body"]
    assert happy["verify_status"] == "draft"
    print("    ✓ happy-path 草稿:method/url/必填占位 body 正确,draft 态")

    print("\n全部通过 ✅  —— 契约摄取成 core 一等能力,消灭逆向猜接口")


if __name__ == "__main__":
    main()

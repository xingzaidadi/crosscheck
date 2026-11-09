"""core/layers.py 离线测试:中性 shop/order 夹具,零业务词。"""
import sys
from pathlib import Path
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.layers import classify, CATS


def main():
    rules = {
        "ui":   ["页面", "展示", "列表", "按钮"],
        "api":  ["提交", "查询", "创建", "删除"],
        "db":   ["落库", "状态", "记录"],
        "ui_only": ["上传", "拖拽"],
    }
    cases = [
        ("shop-01", "产品列表页面展示查询接口的记录",   "three"),
        ("shop-02", "提交订单落库状态",                "api_db"),
        ("shop-03", "图片拖拽上传",                    "ui_only"),
        ("shop-04", "创建商品记录",                    "api_db"),
        ("shop-05", "订单状态页面按钮提交",            "three"),
        ("shop-06", "无任何关键词的描述",              "todo"),
    ]
    ok = 0
    for cid, prose, expected in cases:
        got, _ = classify(prose, rules)
        status = "✓" if got == expected else "✗"
        if got == expected:
            ok += 1
        print(f"  {status} {cid}: 期望={expected} 实际={got}")
    assert ok == len(cases), f"FAIL: {ok}/{len(cases)}"
    print(f"\n分层分类 {ok}/{len(cases)} 通过")


if __name__ == "__main__":
    main()

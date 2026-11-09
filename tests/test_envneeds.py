"""环境需求清单生成器 验证(离线、零业务):终态→归属映射 + workspace 关键词细化 + 分组渲染。"""
import os, sys
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.envneeds import classify_need, build_env_needs, render_md
def main():
    print("环境需求清单生成器 验证:\n")
    refine=[{"match":["受理","转办"],"owner":"env","need":"需受理人账号"},
            {"match":["物料","场景"],"owner":"env","need":"需场景数据"}]
    assert classify_need("✅ PASS","x",refine) is None
    assert classify_need("🔶 FAIL","x",refine)[0]=="defect"
    assert classify_need("⛔ BLOCKED","x",refine)[0]=="product"
    assert classify_need("⏳ NEEDS_TRIGGER","x",refine)[0]=="env"
    assert classify_need("🟡 PENDING·写入","配字段",refine)[0]=="tool"   # 无关键词→工具侧
    o,need=classify_need("🟡 PENDING·写入","点转办按钮",refine)
    assert o=="env" and need=="需受理人账号", (o,need)                      # 命中→环境侧细化
    assert classify_need("🟡 PENDING·UI","选物料联动",refine)[0]=="env"
    print("    ✓ 终态→归属 + 关键词细化(转办/物料→环境侧,普通→工具侧)")
    rows=[("TC1","a","✅ PASS","x"),("TC2","转办单","🟡 PENDING·写入","点转办"),
          ("TC3","建单","🟡 PENDING·写入","配字段"),("TC4","规则","⛔ BLOCKED","待确认")]
    g=build_env_needs(rows,refine)
    assert "TC1" not in [c for v in g.values() for c,_,_ in v]
    assert any(c=="TC2" for c,_,_ in g["env"]) and any(c=="TC3" for c,_,_ in g["tool"]) and g["product"]
    md=render_md(g); assert "环境侧" in md and "工具侧" in md and "产品侧" in md
    print("    ✓ 分组统计 + markdown 渲染(环境/工具/产品分列)")
    print("\n全部通过 ✅  —— 环境需求清单可按『该谁补』自动归类,换系统重跑即更新")
if __name__=="__main__": main()

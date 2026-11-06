"""
状态配方 验证(离线、零业务):按状态名取"造该状态单"的步骤。

跑:python tests/test_state_recipe.py
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

from core.state_recipe import recipe_steps, available_states  # noqa: E402


def main():
    d = Path(tempfile.mkdtemp())
    (d / "orderflow.json").write_text(json.dumps({"states": {
        "DRAFT": {"steps": [{"method": "POST", "url": "/draft", "body": {"t": "x"},
                             "capture": {"code": "data.code"}}]},
        "SUBMITTED": {"steps": [
            {"method": "POST", "url": "/draft", "capture": {"code": "data.code"}},
            {"method": "POST", "url": "/submit", "body_set": {"code": "{{code}}"}}]},
    }}, ensure_ascii=False), encoding="utf-8")

    print("状态配方 验证:\n")
    s = recipe_steps("orderflow", "SUBMITTED", recipes_dir=d)
    assert len(s) == 2 and s[0]["url"] == "/draft" and s[1]["url"] == "/submit", s
    assert s[0]["capture"] == {"code": "data.code"}
    print("    ✓ 取 SUBMITTED 配方:draft→submit 两步,capture 带上")

    assert recipe_steps("orderflow", "DRAFT", recipes_dir=d)[0]["url"] == "/draft"
    assert recipe_steps("orderflow", "NOPE", recipes_dir=d) == []
    assert recipe_steps("nofeature", "DRAFT", recipes_dir=d) == []
    print("    ✓ 无该状态/无该功能 → 空列表(上层据此报'缺配方')")

    assert available_states("orderflow", recipes_dir=d) == ["DRAFT", "SUBMITTED"]
    print("    ✓ available_states 列出已配状态")
    print("\n全部通过 ✅  —— 状态配方(prepare_state→data_prep)就位")


if __name__ == "__main__":
    main()

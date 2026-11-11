"""接入编排器 验证(离线、零业务):注入假探测/登录/爬页/契约,验登录方式探测、
扫描装配、缺口对比(空 workspace vs 已配 workspace)、单路挂掉不崩。
跑:python tests/test_onboard.py
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

from core.workspace import set_workspace  # noqa: E402
from core.onboard import detect_login_method, inspect_workspace, scan_all  # noqa: E402

URL = "https://shop.test.example.cn/home"


def _fakes(**over):
    f = {
        "detect_fn": lambda u: ("https://shop.test.example.cn/login", ["ant-form-item", "ant-btn"]),
        "login_probe_fn": lambda u: {"input_fields": [{"type": "text", "name": "u"},
                                                       {"type": "password", "name": "p"}],
                                     "page_tokens": [], "redirected_offsite": False},
        "sitemap_fn": lambda root, sess: {"pages": [{"title": "t", "url": "u",
                                                     "apis": [{"method": "GET", "path": "/x"}]}]},
        "db_factory": lambda name: None,
        "contracts_fn": lambda path, ctx: [{"http": "POST", "path": "/a/b", "request_dto": "XReq"}],
    }
    f.update(over)
    return f


def _slots(gaps):
    return {g["slot"] for g in gaps}


def test_login_method():
    # 账密框 → credential
    r = detect_login_method([{"type": "text", "name": "u"}, {"type": "password", "name": "p"}])
    assert r["method"] == "credential" and "password-field" in r["signals"], r
    # SSO 标记 → manual
    r = detect_login_method([{"type": "text"}], page_tokens=["通过 SSO 登录"])
    assert r["method"] == "manual" and "sso" in r["signals"], r
    # 跳外站 → manual
    assert detect_login_method([], redirected_offsite=True)["method"] == "manual"
    # 啥都不认 → manual 兜底(低置信)
    r = detect_login_method([])
    assert r["method"] == "manual" and r["confidence"] < 0.5, r
    # 代登框 → act_as 候选
    r = detect_login_method([{"type": "text", "name": "actas_user"},
                             {"type": "password", "name": "p"}])
    assert r["act_as_candidate"] is True, r
    print("    ✓ 登录方式探测:账密→credential / SSO·跳外站→manual / 兜底manual / 代登→act_as")


def test_scan_empty_workspace():
    set_workspace(tempfile.mkdtemp())
    rep = scan_all(URL, site="shop", code_path="/fake/src", db_name="shop_db",
                   write=False, **_fakes())
    k = rep["known"]
    assert k["login"]["method"] == "credential", k["login"]
    assert len(k["pages"]) == 1 and k["api_count"] == 1, k
    assert len(k["contracts"]) == 1, k
    gaps = _slots(rep["gaps"])
    # 扫到的两样(页面、契约)不再问;没配的该问
    assert "page_catalog" not in gaps and "api_contracts" not in gaps, gaps
    assert {"login_method", "credentials", "db_conn", "case_source"} <= gaps, gaps
    print(f"    ✓ 空workspace:扫到页面/契约不问,缺口={sorted(gaps)}")


def test_scan_populated_workspace():
    ws = Path(tempfile.mkdtemp())
    set_workspace(str(ws))
    (ws / "config").mkdir(parents=True)
    (ws / "profiles").mkdir(parents=True)
    (ws / "accounts").mkdir(parents=True)
    (ws / "cases").mkdir(parents=True)
    kb = ws / "knowledge_base"
    for sub in ("schema_map", "contracts", "sitemap", "query_mapping"):
        (kb / sub).mkdir(parents=True)
    (ws / "profiles" / "shop.yaml").write_text(
        "site: shop\nbase_url: https://shop.test.example.cn\nlogin:\n  mode: manual\n",
        encoding="utf-8")
    (ws / "accounts" / "shop.yaml").write_text("roles: {}\n", encoding="utf-8")
    (ws / "config" / "db.yaml").write_text(
        "databases:\n  shop_db:\n    host: 10.0.0.1\n    port: 3306\n    user: ro\n"
        "    password: x\n    database: shop\ndefault_readonly: shop_db\n", encoding="utf-8")
    (kb / "schema_map" / "shop.json").write_text("{}", encoding="utf-8")
    (kb / "contracts" / "shop.json").write_text("{}", encoding="utf-8")
    (kb / "sitemap" / "shop.json").write_text("{}", encoding="utf-8")
    (kb / "business_rules.json").write_text("{}", encoding="utf-8")
    (ws / "cases" / "x.xlsx").write_text("stub", encoding="utf-8")

    have = inspect_workspace("shop", "shop_db")
    assert have["profile"] and have["login_mode"] == "manual" and have["db_conn"], have
    # have 全齐,即便扫不到任何东西也不该再问
    rep = scan_all(URL, site="shop", db_name="shop_db", write=False,
                   **_fakes(sitemap_fn=lambda r, s: {"pages": []},
                            contracts_fn=lambda p, c: []))
    assert rep["gaps"] == [], rep["gaps"]
    print("    ✓ 已配workspace:认得出配齐,零重复追问")


def test_scan_stage_failure_no_crash():
    set_workspace(tempfile.mkdtemp())

    def boom(u):
        raise RuntimeError("探测挂了")
    rep = scan_all(URL, site="shop", write=False, **_fakes(detect_fn=boom))
    assert "detect" in rep["known"]["scan_errors"], rep["known"]["scan_errors"]
    assert rep["known"]["base_url"] == "https://shop.test.example.cn", rep["known"]
    print("    ✓ 单路挂掉记成 scan_error、不崩,其余照常")


def test_scan_db_introspect_sqlite():
    set_workspace(tempfile.mkdtemp())
    dbf = Path(tempfile.mkdtemp()) / "t.db"
    from db.client import DbClient
    c = DbClient(dsn_readonly=f"sqlite:///{dbf}")
    c._ro.connect().close()
    with c._ro.begin() as conn:
        from sqlalchemy import text
        conn.execute(text("CREATE TABLE widget (id INTEGER PRIMARY KEY, stage TEXT)"))
        conn.execute(text("INSERT INTO widget (stage) VALUES ('OPEN'),('DONE')"))
    rep = scan_all(URL, site="shop", db_name="shop_db", write=False,
                   **_fakes(db_factory=lambda name: c))
    assert "widget" in rep["known"]["tables"], rep["known"]["tables"]
    assert "db_conn" not in _slots(rep["gaps"]) or rep["have"]["db_conn"] is False
    print("    ✓ 真sqlite自省:扫出表,db 不再记成连不上")


def test_write_report():
    ws = tempfile.mkdtemp()
    set_workspace(ws)
    rep = scan_all(URL, site="shop", write=True, **_fakes())
    p = Path(rep["report_path"])
    assert p.exists() and json.loads(p.read_text(encoding="utf-8"))["site"] == "shop"
    print(f"    ✓ gap_report 落盘可读回:{p.name}")


def main():
    print("接入编排器 验证:\n")
    test_login_method()
    test_scan_empty_workspace()
    test_scan_populated_workspace()
    test_scan_stage_failure_no_crash()
    test_scan_db_introspect_sqlite()
    test_write_report()
    print("\n全部通过 ✅  —— 扫一遍→对比已配→只问缺口,离线可测、零业务")


if __name__ == "__main__":
    main()


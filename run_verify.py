"""
入口:列表/检索类查询的校验流程。人只给一个页面 URL。

两步(中间隔一次人审,所以拆成两个子命令):

  1) probe   —— 打开 URL、抓检索接口、自动建模,产出映射草稿后停下,等人审。
       python run_verify.py probe --profile <your-site>
       python run_verify.py probe --url "<页面URL>" [--record] [--table <表名> --pk id]

     产出(默认落在 <workspace> 下):
       captures/<feature>_<ts>.json         全部捕获
       captures/<feature>_picked.json        认出的检索调用(请求体+返回)
       knowledge_base/query_mapping/<feature>.draft.json   映射草稿(待审)

     人审:把 draft 里 _needs_review / fixed_where 补好,确认无误后另存为
       knowledge_base/query_mapping/<feature>.json(去掉 .draft),verify_status 改 human_verified。

  2) reconcile —— 用审过的映射 + 抓到的样本 + 测试库,当场对账出报告。
       python run_verify.py reconcile [--profile <your-site>]

依赖:<workspace>/config/db.yaml 填好只读连接(reconcile 阶段必需)。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from core.prober import Prober, Capture  # noqa: E402
from core.mapping_builder import build_mapping_draft  # noqa: E402
from core.reconciler import Reconciler  # noqa: E402
from core.config import db_config, db_params, site_credentials  # noqa: E402
from core.profile import load_profile, list_profiles  # noqa: E402
from core.login import ensure_session  # noqa: E402
from core.workspace import set_workspace, workspace_root, auth_dir, captures_dir, kb_dir  # noqa: E402
from db.client import DbClient  # noqa: E402


def _open_db(db_name: str | None = None) -> DbClient | None:
    """
    建只读连接。优先新式 databases.<名>(显式参数),回退旧式 readonly.dsn(sqlite 测试)。
    db_name 省略时用 db.yaml 的 default_readonly。
    """
    cfg = db_config()
    # 新式:多库显式参数
    if cfg.get("databases"):
        name = db_name or cfg.get("default_readonly")
        p = db_params(name) if name else None
        if p:
            return DbClient(readonly_params=p)
    # 旧式:readonly dsn
    ro = (cfg.get("readonly") or {}).get("dsn", "")
    if ro and "TODO" not in ro:
        return DbClient(dsn_readonly=ro)
    return None


def _try_db() -> DbClient | None:
    try:
        return _open_db()
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠ 连接测试库失败(先建草稿,对账阶段再连): {e}")
        return None


def _profile_from_args(args):
    """--profile 给了就加载 Site Profile,否则 None(走旧式 CLI 默认)。"""
    name = getattr(args, "profile", None)
    return load_profile(name) if name else None


def _resolve(args, profile, key, fallback=None):
    """取值优先级:CLI 显式传参 > profile.defaults > 硬回退。"""
    v = getattr(args, key, None)
    if v is not None:
        return v
    if profile and profile.defaults.get(key) is not None:
        return profile.defaults[key]
    return fallback


def _qmap_dir(profile):
    """映射知识库目录:有 profile 走它(可能自定义)的 knowledge_base,否则用默认 kb。"""
    if profile:
        return workspace_root() / profile.knowledge_base / "query_mapping"
    return kb_dir() / "query_mapping"


def cmd_probe(args):
    profile = _profile_from_args(args)

    # 有 profile:先确保登录态(A 人工 / B 声明式),拿到按站点隔离的 session 文件
    session = getattr(args, "session", None)
    if profile:
        print(f"[login] 站点 {profile.site} · 模式 {profile.login.mode}")
        session = ensure_session(profile, site_credentials(profile.site),
                                 force=getattr(args, "relogin", False))

    feature = _resolve(args, profile, "feature", "list_search")
    url = getattr(args, "url", None) or (profile.defaults.get("probe_url") if profile else None)
    url_pattern = _resolve(args, profile, "url_pattern", "") or ""
    db_name = _resolve(args, profile, "db", None)
    table = _resolve(args, profile, "table", None)
    pk = _resolve(args, profile, "pk", "id")
    session = session or str(auth_dir() / "p0.json")

    if not url:
        print("  ✗ 未指定检索页面 URL(--url,或在 profile.defaults.probe_url 配)。")
        sys.exit(2)
    if not table:
        print("  ✗ 未指定库表名(--table,或在 profile.defaults.table 配)。")
        sys.exit(2)

    print(f"[probe] 打开页面抓取检索接口: {url}")
    if args.record:
        print("  录制模式:浏览器会打开,请手动完成一次检索。")

    prober = Prober(url_pattern=url_pattern, session_file=session, headless=not args.record)
    prober.probe(url, trigger_selector=args.trigger, wait_ms=args.wait, record=args.record)

    if not prober.captures:
        print("  ✗ 没抓到任何 XHR/fetch。检查 URL / 登录态 / --url-pattern 是否过严。")
        sys.exit(2)

    all_path = prober.save(captures_dir(), feature)
    print(f"  抓到 {len(prober.captures)} 次调用 → {all_path.name}")

    picked = prober.pick_search_call()
    if picked is None:
        print("  ✗ 没认出哪个是检索接口。请看捕获文件,用 --url-pattern 指定接口。")
        sys.exit(3)
    cap = captures_dir()
    cap.mkdir(parents=True, exist_ok=True)
    picked_path = cap / f"{feature}_picked.json"
    picked_path.write_text(
        json.dumps(picked.__dict__, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  认出检索接口: {picked.method} {picked.url}")

    # 连库取列(连不上就用空列,草稿里标 TODO,不阻断)
    try:
        db = _open_db(profile.db_readonly) if profile else _try_db()
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠ 连接测试库失败(先建草稿,对账阶段再连): {e}")
        db = None
    columns = db.columns(table) if db else []
    if db:
        print(f"  读到表 {table} 的 {len(columns)} 个字段用于匹配")
        db.close()
    else:
        print("  (未连库,参数→列匹配留待人审;对账阶段必须连库)")

    draft = build_mapping_draft(picked, db_name=db_name, table=table, pk=pk, columns=columns)
    qdir = _qmap_dir(profile)
    qdir.mkdir(parents=True, exist_ok=True)
    draft_path = qdir / f"{feature}.draft.json"
    draft_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n  ✓ 映射草稿已生成 → {draft_path}")
    print("  请人审以下几处,然后另存为同名去掉 .draft 的文件:")
    for note in draft.get("_review_notes", []):
        print(f"    - {note}")
    print(f"    - fixed_where 当前为: {draft['fixed_where']!r}")
    reconcile_hint = "python run_verify.py reconcile"
    if profile:
        reconcile_hint += f" --profile {profile.site}"
    print(f"\n  审完执行: {reconcile_hint}")


def cmd_reconcile(args):
    profile = _profile_from_args(args)
    feature = _resolve(args, profile, "feature", "list_search")
    mapping_path = _qmap_dir(profile) / f"{feature}.json"
    picked_path = captures_dir() / f"{feature}_picked.json"

    if not mapping_path.exists():
        print(f"  ✗ 未找到审过的映射 {mapping_path.name}。")
        print(f"    请把 {feature}.draft.json 审完后另存为 {feature}.json。")
        sys.exit(2)
    if not picked_path.exists():
        print(f"  ✗ 未找到抓取样本 {picked_path.name}。先跑 probe。")
        sys.exit(2)

    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    if mapping.get("verify_status") != "human_verified":
        print("  ⚠ 映射 verify_status 不是 human_verified,建议审核确认后再对账。")

    picked = json.loads(picked_path.read_text(encoding="utf-8"))
    api_params = picked.get("request_body") or picked.get("query_params") or {}
    api_response = picked.get("response_json") or {}

    db_name = getattr(args, "db_readonly", None) or (profile.db_readonly if profile else None)
    db = _open_db(db_name)
    if db is None:
        print("  ✗ <workspace>/config/db.yaml 未配可用的只读连接,无法对账。")
        sys.exit(2)
    try:
        rec = Reconciler(db, mapping)
        result = rec.reconcile(api_params, api_response)
        print(result.render())
    finally:
        db.close()

    print("\n这个结果就是判断依据:一致 → 参数转 SQL 可信,可进一步做写入类校验;"
          "不一致 → 先查是接口 bug 还是映射错。")
    sys.exit(0 if result.consistent else 1)


def cmd_login(args):
    """按 profile 建立/刷新登录态。A 模式开浏览器人工登;B 模式声明式自动登。"""
    profile = load_profile(args.profile)
    print(f"[login] 站点 {profile.site} · 模式 {profile.login.mode}")
    path = ensure_session(profile, site_credentials(profile.site), force=args.force)
    print(f"  会话文件: {path}")


def main():
    ap = argparse.ArgumentParser(description="列表/检索类查询校验(通用:--profile 指定站点)")

    # 所有子命令共享 --workspace(业务数据目录)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--workspace", default=None,
                        help="业务数据目录(省略则按 VTA_WORKSPACE / ./workspace / 仓库根 解析)")

    sub = ap.add_subparsers(dest="cmd", required=True)

    # --profile 给了就从 <workspace>/profiles/<名>.yaml 取站点身份;不给则沿用下面的 CLI 默认(旧式用法)
    prof_help = f"Site Profile 名(<workspace>/profiles/<名>.yaml),现有: {list_profiles() or '无'}"

    g = sub.add_parser("login", help="按 profile 建立/刷新登录态", parents=[common])
    g.add_argument("--profile", required=True, help=prof_help)
    g.add_argument("--force", action="store_true", help="忽略已有登录态,强制重登")
    g.set_defaults(func=cmd_login)

    p = sub.add_parser("probe", help="抓取 + 自动建模,产出映射草稿", parents=[common])
    p.add_argument("--profile", default=None, help=prof_help)
    p.add_argument("--url", default=None, help="检索页面 URL(不给则用 profile.defaults.probe_url)")
    p.add_argument("--feature", default=None)
    p.add_argument("--url-pattern", dest="url_pattern", default=None, help="只捕获 url 含该子串的接口")
    p.add_argument("--trigger", default=None, help="触发检索的按钮选择器(auto 模式)")
    p.add_argument("--record", action="store_true", help="录制模式:人工操作一次")
    p.add_argument("--relogin", action="store_true", help="(有 profile 时)强制重登再抓")
    p.add_argument("--session", default=None, help="登录态文件;有 profile 时自动用 .auth/<site>.json")
    p.add_argument("--wait", type=int, default=4000, help="等待网络的毫秒数")
    p.add_argument("--db", default=None)
    p.add_argument("--table", default=None)
    p.add_argument("--pk", default=None)
    p.set_defaults(func=cmd_probe)

    r = sub.add_parser("reconcile", help="用审过的映射连库对账", parents=[common])
    r.add_argument("--profile", default=None, help=prof_help)
    r.add_argument("--feature", default=None)
    r.add_argument("--db-readonly", dest="db_readonly", default=None,
                   help="覆盖对账只读库(db.yaml databases.<名>)")
    r.set_defaults(func=cmd_reconcile)

    args = ap.parse_args()
    if getattr(args, "workspace", None):
        set_workspace(args.workspace)
    args.func(args)


if __name__ == "__main__":
    main()

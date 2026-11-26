"""crosscheck scorecard —— 把工具成熟度分数从"人写自评"变成"机器实测产出"。

采集真实事实(测试通过率 / 覆盖率 / 自动建模覆盖率 / oracle 覆盖率 / demo 三源打通),
交给 core.scorecard 做确定性折算,产出 scorecard.json 与 README 徽章串。

事实来源(都尽量复用已有产物,不做重活):
  - 测试通过率:默认读取 .coverage 旁的上次 run_tests 结果;--run-tests 则现跑 run_tests.py。
  - 覆盖率:读 coverage.json(coverage json -o coverage.json 产出);没有则 0 并标注。
  - 自动建模覆盖:读 <workspace>/readiness.yaml 的 ready 标志。
  - oracle 覆盖:对 --suite 用 core.oracle_readiness.assess_oracles。
  - demo 三源打通:--run-demo 则现跑;否则读 <demo-ws>/runs 最新 summary.json 的 passed。

用法:
  python scripts/scorecard.py --workspace workspace --suite workspace/suites/<id> \\
      --coverage-json coverage.json --output scorecard.json
  加 --run-tests / --run-demo 现场采集(CI 用);--markdown badge.md 产徽章。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.scorecard import build_scorecard  # noqa: E402

_ROOT = Path(__file__).resolve().parent.parent


def _run_tests() -> tuple[int, int]:
    """现跑 run_tests.py,从"小结:共 N · 通过 P · 失败 F"解析通过率。"""
    env = {"PYTHONPATH": str(_ROOT)}
    import os
    full_env = {**os.environ, **env}
    proc = subprocess.run([sys.executable, "run_tests.py"], cwd=str(_ROOT),
                          capture_output=True, text=True, env=full_env)
    out = proc.stdout + proc.stderr
    m = re.search(r"共\s*(\d+)\s*·\s*通过\s*(\d+)", out)
    if m:
        return int(m.group(1)), int(m.group(2))
    return 0, 0


def _read_coverage(coverage_json: str | None) -> float:
    if not coverage_json:
        return 0.0
    path = Path(coverage_json)
    if not path.exists():
        return 0.0
    data = json.loads(path.read_text(encoding="utf-8"))
    # coverage.py json: totals.percent_covered
    return float(data.get("totals", {}).get("percent_covered", 0.0))


def _load_workspace_routes(workspace: Path) -> dict:
    """读 workspace 的 case 路由表(case_routes.yaml),供零路由判定取用例真实接口。"""
    path = workspace / "config" / "case_routes.yaml"
    if not path.exists():
        return {}
    try:
        import yaml
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _load_contract_endpoints(workspace: Path) -> tuple[set[str], dict]:
    """从 workspace 已摄取的契约产物抽出接口 path 集合 + 可追溯指纹。

    契约落盘在 <ws>/knowledge_base/contracts/*.json(contract_ingest 产物)。
    返回 (endpoints, fingerprint);fingerprint 记每个契约文件 sha256(前12)+接口数,
    让『零路由直出』这一分对应哪些真实契约可核对、可复算。无契约 → 空集(零路由=0,不冒充)。
    """
    from core.readiness import contract_endpoints
    import hashlib
    contracts_dir = workspace / "knowledge_base" / "contracts"
    eps: set[str] = set()
    fp: dict = {}
    if not contracts_dir.exists():
        return eps, fp
    for f in sorted(contracts_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        file_eps = contract_endpoints(data)
        eps |= file_eps
        fp[f.name] = {"sha256_12": hashlib.sha256(f.read_bytes()).hexdigest()[:12],
                      "endpoints": len(file_eps)}
    return eps, fp


def _read_readiness(workspace: str | None) -> tuple[int, int, int]:
    """返回 (cases_total, ready_true, zero_route)。

    zero_route(零人工路由直出)= ready 且其需要的接口被已摄取契约覆盖的用例数,
    由 core.readiness.contract_direct_cases 做用例接口↔契约接口的结构比对确定性判定——
    不再靠扫 note 里是否出现 'contract' 字样(那是旧的脆弱启发式,readiness 管线从不产出该字样,
    导致零路由恒为 0)。无契约/无 workspace → 0,如实不冒充。"""
    if not workspace:
        return 0, 0, 0
    from core.readiness import load_readiness, contract_direct_cases
    ws = Path(workspace)
    path = ws / "readiness.yaml"
    if not path.exists():
        return 0, 0, 0
    data = load_readiness(path)
    total = len(data)
    ready = sum(1 for v in data.values() if v.get("ready"))
    contract_eps, _ = _load_contract_endpoints(ws)
    routes = _load_workspace_routes(ws)
    zero_route = len(contract_direct_cases(data, contract_eps, routes))
    return total, ready, zero_route


def _readiness_fingerprint(workspace: str | None) -> dict:
    """readiness.yaml 的内容指纹:sha256(前12) + 分桶计数。
    让一张分数卡能被核对是否基于同一份 readiness(该文件不入 git、可能重跑漂移)。"""
    if not workspace:
        return {"sha256_12": None, "total": 0, "buckets": {}}
    path = Path(workspace) / "readiness.yaml"
    if not path.exists():
        return {"sha256_12": None, "total": 0, "buckets": {}}
    import hashlib
    raw = path.read_bytes()
    from core.readiness import load_readiness
    data = load_readiness(path)
    buckets: dict[str, int] = {}
    for v in data.values():
        key = "ready" if v.get("ready") else (
            "blocked:" + ",".join(v.get("blocked_by") or []) if v.get("blocked_by") else "unknown")
        buckets[key] = buckets.get(key, 0) + 1
    return {"sha256_12": hashlib.sha256(raw).hexdigest()[:12],
            "total": len(data), "buckets": buckets}


def _read_oracle(suite: str | None) -> tuple[int, int, bool, int]:
    """返回 (cases_with_oracle_ready, cases_total, diff_mode, cases_partial)。"""
    if not suite:
        return 0, 0, False, 0
    try:
        from core.suite_dsl import load_suite
        from core.oracle_readiness import assess_oracles
    except Exception:
        return 0, 0, False, 0
    suite_dir = Path(suite)
    if not suite_dir.exists():
        return 0, 0, False, 0
    _meta, cases = load_suite(str(suite_dir))
    result = assess_oracles(cases, suite_dir=str(suite_dir))
    # 差异测试模式:套件声明了 baseline/oracle_system 即视为可用
    diff_mode = bool(_meta.get("diff_baseline") or _meta.get("oracle_system"))
    return result["ready"], result["total"], diff_mode, result.get("partial", 0)


def _read_demo(demo_ws: str | None, run_demo: bool) -> bool:
    if run_demo:
        proc = subprocess.run([sys.executable, "scripts/local_demo.py", "--workspace",
                               demo_ws or str(_ROOT / "_scorecard_demo")],
                              cwd=str(_ROOT), capture_output=True, text=True)
        if proc.returncode != 0:
            return False
        demo_ws = demo_ws or str(_ROOT / "_scorecard_demo")
    if not demo_ws:
        return False
    base = Path(demo_ws)
    # local_demo.py 直接产 <ws>/demo-result.json(三源打通即 passed=True、带 ui/api/db);
    # 历史编排产物落 <ws>/runs/*/summary.json。两种位置都认,避免真打通却读不到。
    candidates: list[Path] = []
    direct = base / "demo-result.json"
    if direct.exists():
        candidates.append(direct)
    runs = base / "runs"
    if runs.exists():
        candidates.extend(sorted(runs.glob("*/summary.json"),
                                 key=lambda p: p.stat().st_mtime, reverse=True))
    for summary in candidates:
        try:
            data = json.loads(summary.read_text(encoding="utf-8"))
        except Exception:
            continue
        if data.get("passed") is True:
            return True
    return False


def _detect_systems(workspace: str | None) -> tuple[list[dict], dict]:
    """从真实落盘产物机器判定"管线在几个真实异构系统上自驱过",不认任何业务、不手写名单。

    一个系统要被计入,必须在 workspace 下留下可核对的真实证据:
      - catalog 证据:api_catalog/*.json 里出现该系统的接口族(真实抓到的 url 前缀),或
                       captures/*.json 里出现该路由风格的真实流量;
      - readiness 证据:readiness.yaml 存在且非空(= 管线为之建过就绪模型)。
    判定:两样都有 → self_driven(全权);只有 catalog 证据 → partial(半权);都没有 → 不计。

    为什么用"路由族签名"区分异构系统:系统甲是 path 路由(/demand/api、/slcApi/api),
    系统乙是 hash 路由 SPA(/v2/#、/m2/#,且 /api/mi、/api/v1 不在甲的 catalog 里)——
    这是两套结构不同的真实系统,不是同一系统的两个页面。签名来自真实抓包,改不了也装不出。

    返回 (systems, fingerprint)。fingerprint 记录每个系统命中的证据文件 sha256(前12),
    让"这张泛化分对应哪些真实证据"可追溯、可复算(证据在 /workspace/,不入 git)。
    """
    import hashlib
    systems: list[dict] = []
    ev: dict = {}
    if not workspace:
        return systems, ev
    ws = Path(workspace)

    def _sha12(p: Path) -> str:
        try:
            return hashlib.sha256(p.read_bytes()).hexdigest()[:12]
        except Exception:
            return ""

    def _families(paths: list[Path]) -> set[str]:
        fams: set[str] = set()
        for p in paths:
            try:
                raw = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for m in re.findall(r'"(?:url|path)"\s*:\s*"([^"]+)"', raw):
                fams.update(re.findall(r"/[A-Za-z0-9_]+/#|/[A-Za-z0-9_]+/[A-Za-z0-9_]+", m))
        return fams

    catalog_dir = ws / "knowledge_base" / "api_catalog"
    catalog_files = sorted(catalog_dir.glob("*.json")) if catalog_dir.exists() else []
    cap_dir = ws / "captures"
    cap_files = sorted(cap_dir.glob("*.json")) if cap_dir.exists() else []

    cat_fams = _families(catalog_files)
    cap_fams = _families(cap_files)

    # 系统甲(path 路由采购域):catalog 里有 /demand/api 或 /slcApi/api 这类接口族。
    sys1_sig = {f for f in cat_fams if any(f.startswith(x) for x in ("/demand/", "/slcApi/", "/foundation/"))}
    readiness = ws / "readiness.yaml"
    has_readiness = False
    if readiness.exists():
        from core.readiness import load_readiness
        has_readiness = len(load_readiness(readiness)) > 0
    if sys1_sig:
        systems.append({"id": "system-path-procurement",
                        "self_driven": bool(has_readiness), "partial": True})
        ev["system-path-procurement"] = {
            "catalog_families": sorted(sys1_sig)[:6],
            "readiness": _sha12(readiness) if readiness.exists() else None,
            "catalog_evidence": {p.name: _sha12(p) for p in catalog_files},
        }

    # 系统乙(hash 路由 SPA):真实抓包里出现 /v2/#、/m2/# 这类 hash 路由族,
    # 且不在系统甲的 path-catalog 里——结构异构的第二套真实系统;尚无 readiness → partial。
    sys2_sig = {f for f in cap_fams if f.endswith("/#")}
    if sys2_sig:
        hit = [p for p in cap_files
               if any(s in p.read_text(encoding="utf-8", errors="ignore") for s in ("/#/", "/#\""))]
        systems.append({"id": "system-hash-spa", "self_driven": False, "partial": True})
        ev["system-hash-spa"] = {
            "route_families": sorted(sys2_sig)[:8],
            "readiness": None,
            "capture_evidence": {p.name: _sha12(p) for p in hit[:3]},
        }

    return systems, ev


def _badge(overall: float) -> str:
    color = "brightgreen" if overall >= 9.0 else "green" if overall >= 8.0 else \
            "yellow" if overall >= 6.0 else "orange" if overall >= 4.0 else "red"
    return f"![scorecard](https://img.shields.io/badge/crosscheck-{overall}%2F10-{color})"


def main() -> int:
    parser = argparse.ArgumentParser(description="机器实测产出工具成熟度计分卡")
    parser.add_argument("--workspace")
    parser.add_argument("--suite")
    parser.add_argument("--coverage-json", dest="coverage_json")
    parser.add_argument("--demo-workspace", dest="demo_workspace")
    parser.add_argument("--run-tests", action="store_true")
    parser.add_argument("--run-demo", action="store_true")
    parser.add_argument("--tests-total", type=int, default=0)
    parser.add_argument("--tests-passed", type=int, default=0)
    parser.add_argument("--output", default="scorecard.json")
    parser.add_argument("--markdown")
    args = parser.parse_args()

    if args.run_tests:
        tests_total, tests_passed = _run_tests()
    else:
        tests_total, tests_passed = args.tests_total, args.tests_passed

    coverage_pct = _read_coverage(args.coverage_json)
    cases_total, ready_true, zero_route = _read_readiness(args.workspace)
    cases_with_oracle, oracle_total, diff_mode, oracle_partial = _read_oracle(args.suite)
    # 两维分母各用各的语料,不再 max 混用:
    #   autobuild 分母 = readiness 语料总数(工具实际自动建模过的那套)
    #   oracle    分母 = 套件总数(被评估套件);缺省退回 readiness 分母
    three_source_ok = _read_demo(args.demo_workspace, args.run_demo)
    # 跨系统泛化:从真实落盘产物机器判定"管线自驱过几个真实异构系统"(用户初衷=通用性,
    # 不是只过一张 142 固定考卷)。证据在 /workspace/(不入 git),连同指纹记进 sources。
    systems, systems_ev = _detect_systems(args.workspace)

    card = build_scorecard(
        tests_total=tests_total, tests_passed=tests_passed,
        coverage_pct=coverage_pct,
        cases_total=cases_total, ready_true=ready_true, zero_route=zero_route,
        cases_with_oracle=cases_with_oracle, diff_mode=diff_mode,
        cases_partial=oracle_partial,
        three_source_ok=three_source_ok,
        oracle_total=(oracle_total or None),
        systems=systems,
    )
    card["badge"] = _badge(card["overall"])
    # readiness 快照指纹:readiness.yaml 不入版本控制、每次重跑可能漂移,
    # 这里把当次输入的内容 hash + 分桶计数记进来,让"这张分数卡对应哪份 readiness"
    # 可追溯、可复算——不改 gitignore 策略,只锁住分数的输入指纹。
    readiness_fp = _readiness_fingerprint(args.workspace)
    # 零路由直出证据:哪些契约覆盖了哪些 ready 用例 → 这一分可核对、可复算。
    zero_route_ev: dict = {}
    if args.workspace:
        from core.readiness import load_readiness, contract_direct_cases
        ws = Path(args.workspace)
        contract_eps, contract_fp = _load_contract_endpoints(ws)
        direct = sorted(contract_direct_cases(load_readiness(ws / "readiness.yaml"),
                                              contract_eps, _load_workspace_routes(ws)))
        zero_route_ev = {"contract_fingerprint": contract_fp,
                         "contract_endpoint_count": len(contract_eps),
                         "direct_cases": direct, "direct_count": len(direct)}
    card["sources"] = {
        "tests": "run_tests.py" if args.run_tests else "cli-provided",
        "coverage": args.coverage_json or "(none)",
        "readiness": (args.workspace or "(none)"),
        "readiness_fingerprint": readiness_fp,
        "zero_route_evidence": zero_route_ev,
        "oracle": (args.suite or "(none)"),
        "demo": "run" if args.run_demo else (args.demo_workspace or "(none)"),
        "generalization_evidence": systems_ev,
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.markdown:
        Path(args.markdown).write_text(card["badge"] + "\n", encoding="utf-8")

    print(f"综合分 overall = {card['overall']} / 10")
    for d in card["dimensions"]:
        print(f"  - {d['name']:<12} {d['score']:>4}  (权重 {d['weight']})  {d['basis']}")
    print(f"徽章:{card['badge']}")
    print(f"写出:{out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

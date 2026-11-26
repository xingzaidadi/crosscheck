"""crosscheck route-assign —— 契约端点 → 用例候选路由(候选态,人审晋级)。

补上 by_feature(按端点)↔ by_case_id(按用例)缺的那一跳:把契约端点按确定性词匹配
分配给具体用例,产出候选路由 + 『可翻正清单』(这些 unknown 用例接契约后能从 false 翻 true)。

薄驱动:匹配机制都在 core.route_assign(零业务)。本脚本只管 CLI 与落盘/报告。
候选落独立文件 case_routes.candidate.yaml,默认不进就绪流水线;--promote 人审后才晋级。

用法:
  # 无源码,有 OpenAPI/Swagger
  python scripts/route_assign.py --openapi openapi.json --cases cases.json --workspace workspace
  # 有已摄取的契约 json
  python scripts/route_assign.py --contracts workspace/knowledge_base/contracts/<site>.json --cases cases.xlsx
  # 人审晋级:把候选搬进正式 case_routes.yaml
  python scripts/route_assign.py --contracts <...> --cases <...> --promote TC01 --promote TC07
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml  # noqa: E402

from core import contract_ingest as ci  # noqa: E402
from core.case_source import read_cases  # noqa: E402
from core.route_assign import assign_routes  # noqa: E402


def _load_endpoints(args) -> list[dict]:
    if args.contracts:
        data = json.loads(Path(args.contracts).read_text(encoding="utf-8"))
        if isinstance(data, list):           # 裸端点列表(contract_ingest 直出)
            return data
        return data.get("endpoints") or []   # {endpoints:[...]} 包裹形态
    if args.openapi:
        contract = ci.ingest("openapi", args.openapi, site=args.site or "")
        return contract.to_dict().get("endpoints") or []
    raise SystemExit("需提供 --contracts 或 --openapi 之一")


def _load_keywords(path: str | None) -> dict:
    """领域动作词(workspace 侧,零业务由调用方给):每行一个词,或 JSON/YAML 列表/字典。"""
    if not path or not Path(path).is_file():
        return {}
    text = Path(path).read_text(encoding="utf-8")
    try:
        obj = yaml.safe_load(text)
        if isinstance(obj, dict):
            return obj
        if isinstance(obj, list):
            return {str(w): 1 for w in obj}
    except Exception:
        pass
    return {line.strip(): 1 for line in text.splitlines() if line.strip() and not line.startswith("#")}


def _coverage_report(cases, candidates, workspace: str) -> dict:
    """可翻正清单:当前 unknown 用例里,多少条能被契约候选覆盖,readiness 预计升到多少。

    若 workspace 有真实 readiness.yaml,按『当前 false 且被候选覆盖 → 翻 true』口径算真实 X%→Y%;
    否则只报『可分配条数』(无基线,不臆造投影)。
    """
    total = len(cases)
    assigned = {c.case_id for c in candidates}
    rep = {"cases_total": total, "assignable": len(assigned),
           "assignable_rate": round(len(assigned) / total, 4) if total else 0.0,
           "baseline": None}

    path = Path(workspace) / "readiness.yaml"
    if path.is_file():
        from core.readiness import load_readiness, case_endpoints, norm_endpoint
        data = load_readiness(path)
        base_total = len(data) or total
        base_ready = sum(1 for v in data.values() if v.get("ready"))
        base_zero = sum(1 for v in data.values()
                        if v.get("ready") and "contract" in str(v.get("note", "")).lower())
        # 可达性下界:已 ready 用例覆盖的端点集(确知可达,reachable 的可证下界)。
        # 不臆造 reachable——只认已证可达的端点,否则翻正就是灌数。
        routes_path = Path(workspace) / "config" / "case_routes.yaml"
        by_id = {}
        if routes_path.is_file():
            rdoc = yaml.safe_load(routes_path.read_text(encoding="utf-8")) or {}
            by_id = rdoc.get("by_case_id") or {}
        reachable_evidence: set[str] = set()
        for cid, v in data.items():
            if v.get("ready"):
                reachable_evidence |= case_endpoints(cid, "", by_id.get(cid))
        # 候选端点 → 归一化
        cand_ep = {}
        for c in candidates:
            ep = getattr(c, "endpoint", "") or ""
            url = ep.split(" ", 1)[-1] if " " in ep else ep
            cand_ep[c.case_id] = norm_endpoint(url)
        # 只数"现 false、被候选覆盖、且候选端点确知可达"的——这才是真翻正。
        # 候选端点未在已证可达集的,不计(需真实线上探测才能判,凭契约翻=灌数)。
        flips_reachable = [cid for cid in assigned
                           if cid in data and not data[cid].get("ready")
                           and cand_ep.get(cid) in reachable_evidence]
        flips_unproven = [cid for cid in assigned
                          if cid in data and not data[cid].get("ready")
                          and cand_ep.get(cid) not in reachable_evidence]
        flips = len(flips_reachable)
        proj_ready = base_ready + flips
        rep["baseline"] = {
            "total": base_total,
            "ready_before": base_ready, "ready_after": proj_ready,
            "ready_rate_before": round(base_ready / base_total, 4) if base_total else 0.0,
            "ready_rate_after": round(proj_ready / base_total, 4) if base_total else 0.0,
            "zero_route_before": base_zero, "zero_route_after": base_zero + flips,
            "flips": flips,
            "flips_reachable": sorted(flips_reachable),
            "unproven_need_probe": sorted(flips_unproven),
        }
    return rep


def main() -> int:
    parser = argparse.ArgumentParser(description="契约端点→用例候选路由(候选态,人审晋级)")
    parser.add_argument("--contracts", help="已摄取契约 json(contract_ingest 产物)")
    parser.add_argument("--openapi", help="OpenAPI/Swagger 文档(无契约时现摄取)")
    parser.add_argument("--cases", required=True, help="用例文件(xlsx/csv/json/yaml)")
    parser.add_argument("--keywords", help="领域动作词文件(workspace 侧,零业务由你给)")
    parser.add_argument("--site", default="")
    parser.add_argument("--workspace", default="workspace")
    parser.add_argument("--min-score", type=float, default=2.0)
    parser.add_argument("--margin", type=float, default=1.0)
    parser.add_argument("--context-prefix", default="")
    parser.add_argument("--promote", action="append", default=[], help="人审晋级的 case_id(可多次)")
    parser.add_argument("--output")
    args = parser.parse_args()

    endpoints = _load_endpoints(args)
    cases = read_cases(args.cases)
    keywords = _load_keywords(args.keywords)

    candidates = assign_routes(cases, endpoints, keywords=keywords,
                               min_score=args.min_score, margin=args.margin,
                               context_prefix=args.context_prefix)

    ws = Path(args.workspace)
    cand_path = Path(args.output) if args.output else ws / "config" / "case_routes.candidate.yaml"
    cand_path.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "_meta": {"generator": "route_assign", "min_score": args.min_score,
                  "margin": args.margin, "note": "机器候选;未经人审不得晋级;不污染 case_routes.yaml"},
        "by_case_id": {c.case_id: c.to_dict() for c in candidates},
    }
    cand_path.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=True), encoding="utf-8")

    rep = _coverage_report(cases, candidates, args.workspace)
    print(f"候选路由分配:{len(endpoints)} 端点 × {rep['cases_total']} 用例 "
          f"→ {rep['assignable']} 条可翻正({rep['assignable_rate']:.1%})")
    for c in sorted(candidates, key=lambda x: x.case_id):
        print(f"  {c.case_id:10s} → {c.endpoint:28s} score={c.score:.1f}  {c.signals}")
    bl = rep.get("baseline")
    if bl:
        print(f"  可翻正清单(对真实 readiness.yaml,扣除不可达):确知可达 {bl['flips']} 条翻 true")
        print(f"    ready_rate  {bl['ready_rate_before']:.1%} → {bl['ready_rate_after']:.1%}"
              f"  ({bl['ready_before']}/{bl['total']} → {bl['ready_after']}/{bl['total']})")
        if bl.get("flips_reachable"):
            print(f"    可诚实翻正(端点已证可达):{bl['flips_reachable']}")
        if bl.get("unproven_need_probe"):
            print(f"    不可凭契约翻(端点未证可达,需真实线上探测,否则灌数):"
                  f"{bl['unproven_need_probe']}")
        print(f"    zero_route  {bl['zero_route_before']} → {bl['zero_route_after']}(人审晋级并重算后生效)")
    else:
        print("  (workspace 无 readiness.yaml 基线,仅报可分配条数;接真实工作区后出 X%→Y%)")
    print(f"  候选 → {cand_path}")
    print("  候选为 draft 态,默认不进就绪流水线;经 --promote <case_id> 人审晋级后才写正式 case_routes.yaml")

    if args.promote:
        promoted = _promote(ws, candidates, set(args.promote))
        print(f"\n晋级 {len(promoted)} 条到 case_routes.yaml:{sorted(promoted)}")
    return 0


def _promote(ws: Path, candidates, ids: set[str]) -> set[str]:
    """人审晋级:把指定候选搬进正式 case_routes.yaml 的 by_case_id,删 _candidate 元数据。"""
    routes_path = ws / "config" / "case_routes.yaml"
    doc = {}
    if routes_path.is_file():
        doc = yaml.safe_load(routes_path.read_text(encoding="utf-8")) or {}
    by_id = doc.setdefault("by_case_id", {})
    done: set[str] = set()
    for c in candidates:
        if c.case_id in ids:
            node = dict(c.route)
            node.pop("_candidate", None)   # 晋级后去候选元数据
            by_id[c.case_id] = node
            done.add(c.case_id)
    if done:
        routes_path.parent.mkdir(parents=True, exist_ok=True)
        routes_path.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return done


if __name__ == "__main__":
    raise SystemExit(main())

"""crosscheck oracle-autogen —— 用例预期文本 → 结构化 Oracle 候选(候选态,人审晋级)。

补上 oracle 维度缺的那一跳:142 条真实用例的 assertions.source_text 是中文散文,
assess_oracles 要『结构化断言 + 绑定证明层』才判 ready——所以纯文本全 blocked。
本脚本把散文里确定性可抽的 键=值 断言(code=200/version=1/requestStatus=DRAFT…)
抽成 core.oracle 格式的候选,写进独立文件;--promote 人审后才搬进用例 assertions。

分档(与 CP-1' spec_checker 同构):
  - 档位A(默认):core.oracle_autogen 确定性正则抽取,零模型、零网络、可复现。
    实测确定性天花板≈4.2%(只有真正 键=值 的用例能抽),这是数据本质不是代码缺陷。
  - 档位B(--llm,默认关):从 registry 取 oracle_extractor/default(workspace 插件注册才有),
    把抽不出的散文喂 LLM 产候选;没注册→自动降级档位A,不阻塞、不编数。

可复现红线(关键):档位B 的 LLM 抽取**天然不可复现**(同套件两次跑结果不同)。
  为守住 crosscheck『可复现』铁律,产物报告把**每条候选的完整断言**冻结进
  `case_candidates`——这份报告即**候选快照**。晋级分两步,物理隔离模型调用:
    1. 生成快照(可含档位B,一次性离线动作):--llm 跑,产出带断言的报告。
    2. 人审晋级(永远可复现):--from-snapshot <报告> --promote <key>,**只从快照
       确定性写回,绝不重调模型**。于是任何人拿同一快照晋级,结果逐位一致、可 diff。

红线:
  - 只产 status=candidate,绝不置 ready/verify_status;最终信不信由人审(--promote)。
  - core 零业务:领域模式全在 workspace/config/oracle_patterns.yaml,core 只按规则抽。
  - 宁缺毋滥:抽不出就是抽不出,不塞模糊语义凑数。

用法:
  # 档位A 确定性抽取,产候选报告(不改用例)
  python scripts/oracle_autogen.py --suite workspace/suites/<id> --workspace workspace
  # 档位B 生成候选快照(需 workspace 注册 oracle_extractor,默认降级A)
  python scripts/oracle_autogen.py --suite workspace/suites/<id> --workspace workspace --llm --output snap.json
  # 人审晋级(可复现):从快照确定性写回,不重调模型
  python scripts/oracle_autogen.py --suite workspace/suites/<id> --from-snapshot snap.json --promote TC01
  # 档位A 直接晋级(确定性本就可复现,可不带快照)
  python scripts/oracle_autogen.py --suite workspace/suites/<id> --workspace workspace --promote TC01
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml  # noqa: E402

from core.oracle_autogen import generate, summarize  # noqa: E402

_ROOT = Path(__file__).resolve().parent.parent


def _case_files(suite_dir: Path) -> list[Path]:
    return sorted((suite_dir / "cases").glob("*.yaml"))


def _expected_text(case: dict) -> str:
    return str((case.get("assertions") or {}).get("source_text") or "")


def _llm_candidates(text: str, case_id: str) -> list[dict]:
    """档位B:从 registry 取 oracle_extractor/default;没注册→空(降级档位A)。

    插件契约:plan(expected_text=..., case_id=...) -> list[dict](core.oracle 格式候选)。
    core 不硬接模型;真实 LLM 客户端在 workspace/plugins/oracle_extractor.py 里注册。
    """
    try:
        from core.registry import get
        extractor = get("oracle_extractor", "default")
    except Exception:
        extractor = None
    if extractor is None:
        return []
    try:
        out = extractor(expected_text=text, case_id=case_id) or []
    except Exception:
        return []
    # 插件产物一律降级为 candidate,绝不信任其 status
    safe: list[dict] = []
    for item in out:
        if isinstance(item, dict) and item.get("subject") and item.get("operator"):
            entry = dict(item)
            entry["status"] = "candidate"
            entry.setdefault("source", f"llm:{case_id}")
            safe.append(entry)
    return safe


def _layered(candidates: list[dict]) -> dict[str, list[dict]]:
    """把候选按 layer 分进 ui/api/db(写回 assertions 用)。"""
    out: dict[str, list[dict]] = {"ui": [], "api": [], "db": []}
    for c in candidates:
        layer = str(c.get("layer") or "api")
        out.setdefault(layer, []).append({
            "id": c.get("id"), "subject": c.get("subject"),
            "operator": c.get("operator"), "expected": c.get("expected"),
            "proof": layer, "status": "candidate",
            "confidence": c.get("confidence"), "source": c.get("source"),
        })
    return out


def _freeze(c: dict) -> dict:
    """把一条候选冻结成快照条目(保留写回所需全部字段,顺序稳定便于 diff)。"""
    return {
        "id": c.get("id"), "layer": c.get("layer") or "api",
        "subject": c.get("subject"), "operator": c.get("operator"),
        "expected": c.get("expected"), "confidence": c.get("confidence"),
        "source": c.get("source"), "status": "candidate",
    }


def _snapshot_index(snapshot: dict) -> dict[str, list[dict]]:
    """从候选快照报告重建 {case_id/case_key → 冻结候选列表}(可复现晋级用)。"""
    index: dict[str, list[dict]] = {}
    for row in (snapshot.get("cases") or []):
        cands = list(row.get("case_candidates") or [])
        if not cands:
            continue
        cid = str(row.get("case_id") or "")
        ckey = str(row.get("case_key") or "")
        if cid:
            index[cid] = cands
        if ckey:
            index.setdefault(ckey, cands)
    return index


def run(suite: str, workspace: str | None, use_llm: bool,
        promote: list[str], snapshot: dict | None = None) -> dict:
    """抽取候选 + 可选晋级写回。

    snapshot 非空时走**可复现晋级**:候选直接取自快照(不重调模型/不重跑确定性),
    保证任何人拿同一快照晋级结果逐位一致。snapshot 为空时现抽(档位A 本就可复现;
    档位B 现抽仅用于『生成快照』那一次性动作)。
    """
    suite_dir = Path(suite)
    if workspace:
        os.environ.setdefault("CROSSCHECK_WORKSPACE", workspace)
    files = _case_files(suite_dir)
    report = {"suite": str(suite_dir), "cases_total": len(files),
              "det_hit": 0, "llm_hit": 0, "candidates_total": 0,
              "mode": ("snapshot" if snapshot else ("B(llm)" if use_llm else "A(deterministic)")),
              "cases": []}
    promote_set = set(promote or [])
    promoted: list[str] = []
    # 快照晋级:case_id → 冻结的候选列表(完整断言)
    snap_cands = _snapshot_index(snapshot) if snapshot else {}

    for path in files:
        case = yaml.safe_load(path.read_text(encoding="utf-8"))
        case_id = str(case.get("case_id") or path.stem)
        key = str((case.get("source") or {}).get("case_key") or "")
        text = _expected_text(case)

        if snapshot is not None:
            # 可复现晋级:只信快照里冻结的候选,绝不重调模型
            cands = list(snap_cands.get(case_id) or snap_cands.get(key) or [])
            used_llm = any(str(c.get("source", "")).startswith("llm") for c in cands)
        else:
            det = generate(text)  # 档位A:确定性(规则从 workspace 自动装载)
            cands = list(det)
            used_llm = False
            if use_llm and not det:
                llm = _llm_candidates(text, case_id)
                if llm:
                    cands = llm
                    used_llm = True

        if cands:
            if used_llm:
                report["llm_hit"] += 1
            else:
                report["det_hit"] += 1
            report["candidates_total"] += len(cands)

        summary = summarize(cands)
        report["cases"].append({
            "case_id": case_id, "case_key": key,
            "candidates": len(cands),
            "high": len(summary["high"]),
            "source": "llm" if used_llm else ("det" if cands else "none"),
            # 冻结完整断言 → 报告即候选快照,可复现晋级/人审/diff
            "case_candidates": [_freeze(c) for c in cands],
        })

        # 人审晋级:把候选写回该用例的 assertions(draft 态,不动 source_text)
        if cands and (key in promote_set or case_id in promote_set
                      or any(case_id.endswith("/" + p) for p in promote_set)):
            layered = _layered(cands)
            assertions = case.setdefault("assertions", {})
            for layer in ("ui", "api", "db"):
                if layered.get(layer):
                    assertions[layer] = layered[layer]
            case.setdefault("approval", {})["status"] = "draft"
            path.write_text(yaml.safe_dump(case, allow_unicode=True, sort_keys=False),
                            encoding="utf-8")
            promoted.append(case_id)

    report["promoted"] = promoted
    report["det_rate"] = round(report["det_hit"] / len(files), 4) if files else 0.0
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="用例预期文本 → 结构化 Oracle 候选(候选态,人审晋级)")
    ap.add_argument("--suite", required=True)
    ap.add_argument("--workspace")
    ap.add_argument("--llm", action="store_true", help="开档位B(需 workspace 注册 oracle_extractor,默认降级A)")
    ap.add_argument("--from-snapshot", dest="from_snapshot",
                    help="从候选快照报告可复现晋级(只从快照写回,不重调模型)")
    ap.add_argument("--promote", action="append", default=[], help="人审晋级的 case_key/case_id(可多次)")
    ap.add_argument("--output", default="oracle-autogen.json")
    args = ap.parse_args()

    snapshot = None
    if args.from_snapshot:
        snapshot = json.loads(Path(args.from_snapshot).read_text(encoding="utf-8"))

    report = run(args.suite, args.workspace, args.llm, args.promote, snapshot=snapshot)
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"套件 {report['cases_total']} 条 · 模式 {report['mode']}")
    print(f"  确定性抽出候选的用例 {report['det_hit']} = {report['det_rate']:.1%}"
          f"(确定性天花板,数据本质)")
    if report["llm_hit"]:
        print(f"  档位B(LLM)补抽 {report['llm_hit']} 条")
    print(f"  候选总数 {report['candidates_total']}")
    if report["promoted"]:
        print(f"  已人审晋级写回 assertions:{', '.join(report['promoted'])}")
    print(f"写出:{args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

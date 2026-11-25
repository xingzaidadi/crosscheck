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

红线:
  - 只产 status=candidate,绝不置 ready/verify_status;最终信不信由人审(--promote)。
  - core 零业务:领域模式全在 workspace/config/oracle_patterns.yaml,core 只按规则抽。
  - 宁缺毋滥:抽不出就是抽不出,不塞模糊语义凑数。

用法:
  # 档位A 确定性抽取,产候选报告(不改用例)
  python scripts/oracle_autogen.py --suite workspace/suites/<id> --workspace workspace
  # 档位B(需 workspace 注册 oracle_extractor 插件,默认降级A)
  python scripts/oracle_autogen.py --suite workspace/suites/<id> --workspace workspace --llm
  # 人审晋级:把某用例的候选写回它的 assertions(draft 态)
  python scripts/oracle_autogen.py --suite workspace/suites/<id> --promote TC01 --promote TC07
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


def run(suite: str, workspace: str | None, use_llm: bool,
        promote: list[str]) -> dict:
    suite_dir = Path(suite)
    if workspace:
        os.environ.setdefault("CROSSCHECK_WORKSPACE", workspace)
    files = _case_files(suite_dir)
    report = {"suite": str(suite_dir), "cases_total": len(files),
              "det_hit": 0, "llm_hit": 0, "candidates_total": 0,
              "mode": "B(llm)" if use_llm else "A(deterministic)", "cases": []}
    promote_set = set(promote or [])
    promoted: list[str] = []

    for path in files:
        case = yaml.safe_load(path.read_text(encoding="utf-8"))
        case_id = str(case.get("case_id") or path.stem)
        key = str((case.get("source") or {}).get("case_key") or "")
        text = _expected_text(case)

        det = generate(text)  # 档位A:确定性(规则从 workspace 自动装载)
        cands = list(det)
        used_llm = False
        if use_llm and not det:
            llm = _llm_candidates(text, case_id)
            if llm:
                cands = llm
                used_llm = True

        if cands:
            if det:
                report["det_hit"] += 1
            if used_llm:
                report["llm_hit"] += 1
            report["candidates_total"] += len(cands)

        summary = summarize(cands)
        report["cases"].append({
            "case_id": case_id, "case_key": key,
            "candidates": len(cands),
            "high": len(summary["high"]), "source": "llm" if used_llm else ("det" if det else "none"),
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
    ap.add_argument("--promote", action="append", default=[], help="人审晋级的 case_key/case_id(可多次)")
    ap.add_argument("--output", default="oracle-autogen.json")
    args = ap.parse_args()

    report = run(args.suite, args.workspace, args.llm, args.promote)
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

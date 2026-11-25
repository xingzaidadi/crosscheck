"""scripts/oracle_autogen.py 端到端:确定性抽取 → 候选报告 → 人审晋级写回。

离线零业务:构造一个 mini 套件(含 code=200/version=1/requestStatus=DRAFT 的散文预期),
验证 ①确定性抽出 api 候选 ②--promote 把候选写回用例 assertions(draft 态,不动 source_text)
③抽不出的散文用例保持空(宁缺毋滥,不塞模糊语义)④档位B 无插件时降级 A 不崩。
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import yaml  # noqa: E402

from scripts.oracle_autogen import run  # noqa: E402


def _mk_suite(d: Path) -> Path:
    suite = d / "mini"
    (suite / "cases").mkdir(parents=True)
    (suite / "suite.yaml").write_text(
        yaml.safe_dump({"schema_version": 1, "suite_id": "mini", "title": "mini"},
                       allow_unicode=True), encoding="utf-8")
    # 可抽:含 code=200 / version=1 / requestStatus=DRAFT
    (suite / "cases" / "TC01.yaml").write_text(yaml.safe_dump({
        "schema_version": 1, "case_id": "mini/TC01", "suite_id": "mini",
        "source": {"case_key": "TC01"},
        "assertions": {"source_text": "返回 code=200，requestStatus=DRAFT，version=1",
                       "ui": [], "api": [], "db": []},
        "evidence": {"required": ["api_response"]},
    }, allow_unicode=True, sort_keys=False), encoding="utf-8")
    # 抽不出:纯中文叙述(字段联动带出…),确定性无 键=值
    (suite / "cases" / "TC02.yaml").write_text(yaml.safe_dump({
        "schema_version": 1, "case_id": "mini/TC02", "suite_id": "mini",
        "source": {"case_key": "TC02"},
        "assertions": {"source_text": "选择实际需求人后，自动带出需求部门与提单人", "api": []},
    }, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return suite


def test_deterministic_extract_and_promote():
    with tempfile.TemporaryDirectory() as tmp:
        suite = _mk_suite(Path(tmp))
        # 用仓库真实规则(workspace/config/oracle_patterns.yaml)跑确定性抽取
        rep = run(str(suite), workspace=str(ROOT / "workspace"), use_llm=False, promote=["TC01"])

        # ① 确定性只抽中 TC01(宁缺毋滥:TC02 纯散文抽不出)
        assert rep["det_hit"] == 1, rep["det_hit"]
        assert rep["candidates_total"] >= 3, rep  # code/version/requestStatus 至少 3

        # ② 晋级把候选写回 TC01.assertions.api(draft 态),TC02 不动
        tc01 = yaml.safe_load((suite / "cases" / "TC01.yaml").read_text(encoding="utf-8"))
        api = tc01["assertions"]["api"]
        assert api, "TC01 应被写回结构化 api 断言"
        subjects = {a["subject"] for a in api}
        assert {"code", "version", "requestStatus"} <= subjects, subjects
        assert all(a["status"] == "candidate" for a in api)   # 绝不自动过闸
        assert tc01["approval"]["status"] == "draft"
        assert tc01["assertions"]["source_text"], "source_text 原文保留不动"

        tc02 = yaml.safe_load((suite / "cases" / "TC02.yaml").read_text(encoding="utf-8"))
        assert not (tc02["assertions"].get("api") or []), "抽不出的用例不塞候选"
    print("  ✓ 确定性抽 code/version/requestStatus → 候选 → --promote 写回 draft 态")


def test_ladder_b_degrades_without_plugin():
    # 档位B 开但无 oracle_extractor 插件 → 自动降级档位A,不崩、不编数
    with tempfile.TemporaryDirectory() as tmp:
        suite = _mk_suite(Path(tmp))
        rep = run(str(suite), workspace=str(ROOT / "workspace"), use_llm=True, promote=[])
        assert rep["llm_hit"] == 0, "无插件时档位B 不产出"
        assert rep["det_hit"] == 1, "降级档位A 仍确定性抽中 TC01"
    print("  ✓ 档位B 无插件自动降级档位A(默认关、不阻塞、不编数)")


def main():
    test_deterministic_extract_and_promote()
    test_ladder_b_degrades_without_plugin()
    print("\n全部通过 ✅  —— oracle 确定性抽取管线接线(候选→人审晋级),档位B 可开关")


if __name__ == "__main__":
    main()

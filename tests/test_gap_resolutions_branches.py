"""gap_resolutions 分支覆盖(离线、零业务):缺口决议的校验/装载/应用/模板。

run_tests.py 把每个 test_*.py 当脚本跑(returncode==0 即过),纯 pytest 风格不贡献覆盖。
本文件 main()+assert 真实执行,补 validate 的各细分错误、load 的 json/yaml/报错、
index 的类型错配、apply 的 MANUAL_ONLY 确认不自动化 + oracle/fixture 应用、write_template。
"""
import json
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

from core.gap_resolutions import (  # noqa: E402
    load_resolutions, validate_resolutions, resolution_index,
    apply_resolutions, write_template,
)


def test_validate_structural_errors():
    assert validate_resolutions({}) == ["resolutions must be an array"]
    assert validate_resolutions({"resolutions": "nope"}) == ["resolutions must be an array"]
    # 非对象条目
    errs = validate_resolutions({"resolutions": ["x"]})
    assert any("must be an object" in e for e in errs), errs
    # 缺 gap_id + 无效 type + 无效 status 一次打三类
    errs = validate_resolutions({"resolutions": [
        {"resolution_type": "nope", "status": "weird"}]})
    assert any("gap_id is required" in e for e in errs)
    assert any("resolution_type is invalid" in e for e in errs)
    assert any("status must be" in e for e in errs)
    print("  ✓ validate:非数组/非对象/缺gap_id/无效type/无效status 全报")


def test_validate_duplicate_and_value_rules():
    # 重复 gap_id
    errs = validate_resolutions({"resolutions": [
        {"gap_id": "g", "resolution_type": "manual", "status": "pending"},
        {"gap_id": "g", "resolution_type": "manual", "status": "pending"}]})
    assert any("duplicated" in e for e in errs), errs
    # approved 非 manual 必须有非空 value
    errs = validate_resolutions({"resolutions": [
        {"gap_id": "g", "resolution_type": "binding", "status": "approved",
         "approved_by": "qa", "value": {}}]})
    assert any("non-empty" in e for e in errs), errs
    # binding value 缺 target/endpoint… 关键键
    errs = validate_resolutions({"resolutions": [
        {"gap_id": "g", "resolution_type": "binding", "status": "approved",
         "approved_by": "qa", "value": {"irrelevant": "x"}}]})
    assert any("binding value requires" in e for e in errs), errs
    # fixture value 缺 strategy/recipe/steps/name
    errs = validate_resolutions({"resolutions": [
        {"gap_id": "g", "resolution_type": "fixture", "status": "approved",
         "approved_by": "qa", "value": {"irrelevant": "x"}}]})
    assert any("fixture value requires" in e for e in errs), errs
    # 合法 manual approved 无需 value → 无错
    assert validate_resolutions({"resolutions": [
        {"gap_id": "g", "resolution_type": "manual", "status": "approved",
         "approved_by": "qa"}]}) == []
    print("  ✓ validate:重复gap_id、approved空value、binding/fixture关键键、manual豁免")


def test_load_resolutions_json_yaml_and_errors():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        assert load_resolutions(None) == {"schema_version": 1, "resolutions": []}
        # yaml
        yp = d / "r.yaml"
        yp.write_text(yaml.safe_dump({"schema_version": 1, "resolutions": []}), encoding="utf-8")
        assert load_resolutions(yp)["schema_version"] == 1
        # json
        jp = d / "r.json"
        jp.write_text(json.dumps({"schema_version": 1, "resolutions": [
            {"gap_id": "g", "resolution_type": "manual", "status": "pending"}]}), encoding="utf-8")
        assert len(load_resolutions(jp)["resolutions"]) == 1
        # 非法内容抛 ValueError
        bad = d / "bad.yaml"
        bad.write_text(yaml.safe_dump({"resolutions": [{"status": "approved"}]}), encoding="utf-8")
        try:
            load_resolutions(bad)
        except ValueError as e:
            assert "invalid gap resolutions" in str(e)
        else:
            raise AssertionError("非法决议必须抛 ValueError")
    print("  ✓ load_resolutions:None/yaml/json 读取,非法内容抛 ValueError")


def test_resolution_index_type_mismatch():
    gap_report = {"gaps": [{"gap_id": "g1", "type": "ORACLE_REVIEW_REQUIRED"}]}
    # resolution_type 与 gap.type 期望错配 → 记错、不入 index
    idx, errs = resolution_index(
        {"resolutions": [{"gap_id": "g1", "resolution_type": "binding", "status": "approved"}]},
        gap_report)
    assert idx == {} and any("type mismatch" in e for e in errs), (idx, errs)
    # 正确匹配 → 入 index
    idx, errs = resolution_index(
        {"resolutions": [{"gap_id": "g1", "resolution_type": "oracle", "status": "approved"}]},
        gap_report)
    assert "g1" in idx and errs == []
    print("  ✓ resolution_index:类型错配记错不入表,正确匹配入表")


def _manual_plan():
    gap = {"case_id": "suite/C1", "gap_id": "gap:suite/C1:manual", "type": "MANUAL_ONLY",
           "layer": "manual", "reason": "manual only"}
    return {"gap_report": {"gaps": [gap]},
            "readiness": [{"case_id": "suite/C1", "status": "BLOCKED", "blocking_gaps": [gap]}],
            "binding_candidates": [], "oracle_plan": [], "fixture_requirements": []}, gap


def test_apply_manual_only_acknowledged_not_automatable():
    plan, gap = _manual_plan()
    updated, audit = apply_resolutions(plan, {"resolutions": [
        {"gap_id": gap["gap_id"], "resolution_type": "manual", "status": "approved",
         "approved_by": "qa"}]})
    # MANUAL_ONLY 即便被确认也不进 effective_approved → 仍 BLOCKED、仍算残留
    assert updated["readiness"][0]["status"] == "BLOCKED"
    assert updated["gap_report"]["total"] == 1
    assert audit["approved"] == 0 and audit["acknowledged_manual"] == 1
    print("  ✓ apply:MANUAL_ONLY 被确认也不自动化(acknowledged_manual 单列,仍 BLOCKED)")


def test_apply_oracle_and_fixture_configuration():
    oracle_gap = {"case_id": "suite/C1", "gap_id": "gap:suite/C1:api:oracle_review_required",
                  "type": "ORACLE_REVIEW_REQUIRED", "layer": "api", "reason": "r"}
    fixture_gap = {"case_id": "suite/C1", "gap_id": "gap:suite/C1:fixture",
                   "type": "FIXTURE_MISSING", "layer": "fixture", "reason": "r"}
    plan = {"gap_report": {"gaps": [oracle_gap, fixture_gap]},
            "readiness": [{"case_id": "suite/C1", "status": "BLOCKED",
                           "blocking_gaps": [oracle_gap, fixture_gap]}],
            "binding_candidates": [],
            "oracle_plan": [{"case_id": "suite/C1", "layer": "api", "status": "PENDING",
                             "missing_inputs": ["expected"], "configuration": {}}],
            "fixture_requirements": [{"consumers": ["suite/C1"], "preferred_strategy": "",
                                      "missing_inputs": ["strategy"]}]}
    answers = {"resolutions": [
        {"gap_id": oracle_gap["gap_id"], "resolution_type": "oracle", "status": "approved",
         "approved_by": "qa", "value": {"operator": "equals", "expected": 200}},
        {"gap_id": fixture_gap["gap_id"], "resolution_type": "fixture", "status": "approved",
         "approved_by": "qa", "value": {"strategy": "api-seed"}}]}
    updated, audit = apply_resolutions(plan, answers)
    assert updated["oracle_plan"][0]["status"] == "CONFIGURED"
    assert updated["oracle_plan"][0]["missing_inputs"] == []
    assert updated["fixture_requirements"][0]["missing_inputs"] == []
    assert updated["fixture_requirements"][0]["preferred_strategy"] == {"strategy": "api-seed"}
    assert updated["readiness"][0]["status"] == "READY" and audit["approved"] == 2
    print("  ✓ apply:oracle→CONFIGURED、fixture→填充 strategy,两 gap 清后 READY")


def test_write_template_seeds_and_preserves_existing():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "template.yaml"
        gap_report = {"gaps": [
            {"gap_id": "g1", "type": "BINDING_REVIEW_REQUIRED", "reason": "bind"},
            {"gap_id": "g2", "type": "MANUAL_ONLY", "reason": "manual"}]}
        # 首次生成:pending 态 + 类型模板
        write_template(gap_report, out)
        doc = yaml.safe_load(out.read_text(encoding="utf-8"))
        rows = {r["gap_id"]: r for r in doc["resolutions"]}
        assert rows["g1"]["resolution_type"] == "binding" and rows["g1"]["status"] == "pending"
        assert rows["g1"]["value"] == {"target": ""}
        assert rows["g1"]["notes"] == "bind"
        # 已有答案(approved)必须被保留,不被模板覆盖
        existing = {"resolutions": [{"gap_id": "g1", "status": "approved",
                                     "approved_by": "qa", "value": {"target": "/api"}}]}
        write_template(gap_report, out, existing=existing)
        doc2 = yaml.safe_load(out.read_text(encoding="utf-8"))
        g1 = next(r for r in doc2["resolutions"] if r["gap_id"] == "g1")
        assert g1["status"] == "approved" and g1["value"] == {"target": "/api"}
    print("  ✓ write_template:按类型播种 pending 模板,已有答案原样保留")


def main():
    test_validate_structural_errors()
    test_validate_duplicate_and_value_rules()
    test_load_resolutions_json_yaml_and_errors()
    test_resolution_index_type_mismatch()
    test_apply_manual_only_acknowledged_not_automatable()
    test_apply_oracle_and_fixture_configuration()
    test_write_template_seeds_and_preserves_existing()
    print("\n全部通过 ✅  —— gap_resolutions 分支覆盖(校验/装载/错配/应用/模板)")


if __name__ == "__main__":
    main()

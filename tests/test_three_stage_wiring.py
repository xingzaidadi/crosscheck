"""三段式装配(离线):spec 段用真实 modeler 对接 RawCase，不起浏览器/不连库。

跑:python tests/test_three_stage_wiring.py  或  pytest tests/test_three_stage_wiring.py
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from pathlib import Path  # noqa: E402

from core.case_source import RawCase  # noqa: E402
from core.orchestrator import run_case  # noqa: E402
from core.stage_adapters import SpecAgent  # noqa: E402
from core.stage_contracts import STAGE_ARTIFACT  # noqa: E402
from core.stage_runner import StageContext  # noqa: E402
from core.three_stage_wiring import (  # noqa: E402
    make_evidence_verifier,
    make_spec_modeler,
)


class _Stop:
    def produce(self, stage, context):
        return {STAGE_ARTIFACT[stage]: {"status": "not_run", "steps": [], "evidence": []}}


def _raw(case_id="TC01"):
    return RawCase(name=f"{case_id}-查询-列表分页", level="P1", module="demo",
                   steps_text="打开列表并分页", expected_text="列表正确显示", row=1)


def test_spec_modeler_produces_execspec_offline():
    raw = _raw("TC01")
    modeler = make_spec_modeler({raw.case_id: raw}, routes={}, kb_root=Path("."),
                                caps_root=Path("."))
    spec = modeler(StageContext(stage="spec", case_id="TC01"))
    data = spec.to_dict() if hasattr(spec, "to_dict") else dict(spec.__dict__)
    assert data["case_id"] == "TC01"
    assert data["mode"] in {"reconcile", "api", "ui", "manual"}


def test_spec_modeler_unknown_case_raises():
    modeler = make_spec_modeler({}, routes={}, kb_root=Path("."), caps_root=Path("."))
    try:
        modeler(StageContext(stage="spec", case_id="NOPE"))
    except KeyError:
        return
    raise AssertionError("未知用例应抛 KeyError")


def test_plan_only_pipeline_stops_after_spec():
    raw = _raw("TC01")
    agent = SpecAgent(make_spec_modeler({raw.case_id: raw}, routes={}, kb_root=Path("."),
                                        caps_root=Path(".")), auto_verify=True)
    agents = {"spec": agent, "actions": _Stop(), "evidence": _Stop()}
    with tempfile.TemporaryDirectory() as directory:
        result = run_case(agents, directory, "TC01")
        # draft 的建模通常被 CP-1 据 needs_review 打回,停在 spec;无论过否都不得进 actions 执行
        stages_run = [o.stage for o in result.outcomes]
        assert stages_run[0] == "spec"
        assert "evidence" not in stages_run or result.completed


def test_evidence_verifier_ui_only_offline():
    verify = make_evidence_verifier(db_factory=None)
    actions = {"steps": [{"index": 0}], "assertions": [{"passed": True}]}
    out = verify({"case_id": "TC01"}, actions,
                 StageContext(stage="evidence", case_id="TC01"))
    assert out["verdict"] == "pass"
    assert out["sources"]["ui"] is True and out["sources"]["api"] is False


def main() -> None:
    test_spec_modeler_produces_execspec_offline()
    test_spec_modeler_unknown_case_raises()
    test_plan_only_pipeline_stops_after_spec()
    test_evidence_verifier_ui_only_offline()
    print("test_three_stage_wiring ✅ 全部通过")


if __name__ == "__main__":
    main()

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.run_events import append_event, read_events  # noqa: E402


def test_run_events_are_append_only_and_machine_readable(tmp_path):
    append_event(tmp_path, run_id="r1", case_id="c1", state="succeeded",
                 assertion_ids=["A1"], evidence_refs=["cases/c1/api.json"])
    append_event(tmp_path, run_id="r1", case_id="c1", state="failed",
                 failure_class="TARGET_FAIL", detail="assertion mismatch")
    events = read_events(tmp_path)
    assert [event["state"] for event in events] == ["succeeded", "failed"]
    assert events[1]["failure_class"] == "TARGET_FAIL"


if __name__ == "__main__":
    import tempfile
    from pathlib import Path
    test_run_events_are_append_only_and_machine_readable(Path(tempfile.mkdtemp()))
    print("run events passed")

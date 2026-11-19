from core.ui_task_queue import build_task_queue, queue_summary


def test_readiness_gaps_become_assignable_tasks():
    report = {"cases": [
        {"case_id": "TC1", "status": "UI_BLOCKED", "reason": "规则待确认"},
        {"case_id": "TC2", "status": "UI_BINDING_REQUIRED", "reason": "no UI action binding"},
        {"case_id": "TC3", "status": "UI_EXECUTABLE"},
    ]}
    tasks = build_task_queue(report)
    assert [task["type"] for task in tasks] == ["business_clarification", "binding_replay"]
    assert queue_summary(tasks)["open"] == 2


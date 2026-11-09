"""core/prep.py 离线测试:中性 cfg,验三目标态(draft/pending/accept)步骤结构,零业务。"""
import sys
from pathlib import Path
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.prep import build_prep, TARGETS

CFG = {
    "draft_url": "/x/draft", "submit_url": "/x/submit", "code_path": "data.code",
    "code_field": "orderCode", "version_field": "version",
    "pending_value": "PENDING", "accept_value": "ACCEPTED",
    "item_table": "x_item", "item_where": "code='{{code}}'",
    "assoc_table": "x_item_tpl", "assoc_where": "code='{{code}}' AND tpl='T'",
    "with_template": True, "template_item": {"templateCode": "T", "templateVersion": 1},
    "save_url": "/x/tpl/save", "save_body": {"code": "{{code}}", "itemId": "{{itemId}}", "templateId": "{{assocId}}", "dataValue": "{}"},
    "status_table": "x_req", "status_col": "status", "parent_where": "code='{{code}}'",
    "bk_table": "x_proc", "bk_col": "bpm_key", "bk_where": "code='{{code}}'",
    "bpm": {"base_url": "https://bpm", "session": "s.json", "url": "/approve", "body": {"businessKey": "{{bk}}"}},
}


def _kinds(steps):
    out = []
    for s in steps:
        if "db_wait" in s: out.append("wait")
        elif "db_capture" in s: out.append("cap")
        elif s.get("url"): out.append(s["url"])
    return out


def main():
    # draft:只 draft + 抓 itemId/assocId
    d = build_prep("draft", CFG)
    assert _kinds(d) == ["/x/draft", "cap"], _kinds(d)
    assert d[0]["body_set"]["itemList.0.templateList"][0]["templateCode"] == "T"
    print("    ✓ draft:draft 带模板 + 抓 itemId/assocId,止于建关联")

    # pending:+ 存模板数据 + submit(回带 id)+ 等 PENDING_APPROVE
    p = build_prep("pending", CFG)
    assert "/x/tpl/save" in _kinds(p) and "/x/submit" in _kinds(p), _kinds(p)
    sub = [s for s in p if s.get("url") == "/x/submit"][0]
    assert sub["body_set"]["itemList.0.id"] == "{{itemId}}", sub
    assert sub["body_set"]["itemList.0.templateList"][0]["id"] == "{{assocId}}", sub
    assert p[-1]["db_wait"]["equals"] == "PENDING"
    print("    ✓ pending:存模板数据 → submit 回带 item/关联 id → 等审批中态")

    # accept:pending + BPM 审批 + 等受理态
    a = build_prep("accept", CFG)
    assert "/approve" in _kinds(a) and a[-1]["db_wait"]["equals"] == "ACCEPTED", _kinds(a)
    print("    ✓ accept:+ 查 businessKey → BPM 审批 → 等 TO_ACCEPT")

    # 无模板:不注入 templateList、不存模板数据
    cfg2 = {**CFG, "with_template": False}
    p2 = build_prep("pending", cfg2)
    assert "templateList" not in str(p2[0]["body_set"]) and "/x/tpl/save" not in _kinds(p2)
    print("    ✓ with_template=False:不带模板,退回普通提交")
    print("\n前置参数化 通过 ✅")


if __name__ == "__main__":
    main()

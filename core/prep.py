"""C 前置造数参数化(通用、零业务):按"目标态 + 是否带模板"生成 data_prep 步骤流水线,
取代手抄多坨 YAML 锚点。环境一变(如提交须带模板)只改参数,不重写整段。

目标态 target:
  draft   → 仅 draft(可选带模板关联),止于草稿态
  pending → draft(+模板+存数据)→ submit,止于审批中态(pending_value)
  accept  → pending + 查 businessKey → 审批 → 等目标态(accept_value)

零业务:所有 URL/字段名/模板三要素/dataValue/状态值/库表名由调用方(workspace)用 cfg 传入;
core 只负责"按目标态把这些拼成步骤序列"。纯函数、可测。
"""
from __future__ import annotations

from typing import Any

TARGETS = ("draft", "pending", "accept")


def build_prep(target: str, cfg: dict) -> list[dict]:
    """按目标态生成 data_prep 步骤列表。cfg(全部 workspace 传,零业务):
      draft_url, submit_url, code_path, item_table, item_id_col,
      with_template(bool), assoc_table, assoc_match(dict: 建关联行的 where 片段),
      template_item(dict: 一条 templateList 元素), save_url, save_body(dict),
      bpm{base_url,session,url,body}, status_table, status_col, pending_value, accept_value(目标态值),
      item_list_key(默认 itemList)。
    返回步骤序列(与 case_routes 的 data_prep 同结构),供 modeler/engine 执行。"""
    if target not in TARGETS:
        raise ValueError(f"未知目标态: {target}(支持 {TARGETS})")
    ilk = cfg.get("item_list_key", "itemList")
    wt = cfg.get("with_template")
    tpl_item = cfg.get("template_item")
    cf = cfg["code_field"]          # 父单号字段名(业务,workspace 传),core 不写死
    vf = cfg.get("version_field", "version")
    steps: list[dict] = []

    # ① draft(可选带模板关联:嵌套 body_set 注入 itemList.0.templateList)
    draft_bodyset: dict[str, Any] = {cf: "", vf: 1}
    if wt and tpl_item:
        draft_bodyset[f"{ilk}.0.templateList"] = [dict(tpl_item)]
    steps.append({"method": "POST", "url": cfg["draft_url"], "body_set": draft_bodyset,
                  "capture": {"code": cfg["code_path"]}})

    # ② 查 draft 产出的 itemId(+ 带模板时查关联 id)
    cap: dict[str, Any] = {"itemId": {"table": cfg["item_table"], "column": cfg.get("item_id_col", "id"),
                                      "where": cfg["item_where"], "poll_until_nonempty": True, "timeout_s": 12}}
    if wt:
        cap["assocId"] = {"table": cfg["assoc_table"], "column": "id", "where": cfg["assoc_where"],
                          "poll_until_nonempty": True, "timeout_s": 12}
    steps.append({"db_capture": cap})

    if target == "draft":
        return steps

    # ③ 带模板:提交前先存一条有效模板数据
    if wt and cfg.get("save_url"):
        steps.append({"method": "POST", "url": cfg["save_url"], "body": dict(cfg["save_body"])})
        steps.append({"db_capture": {"ver": {"table": cfg["status_table"], "column": "version",
                                             "where": cfg["parent_where"]}}})
    # ④ submit(带模板时回带 item.id + 关联 id,保住模板数据链接)
    sc = cfg.get("status_col", "status")
    sub_bodyset: dict[str, Any] = {cf: "{{code}}", vf: "{{ver}}"}
    if wt:
        sub_bodyset[f"{ilk}.0.id"] = "{{itemId}}"
        sub_bodyset[f"{ilk}.0.{cf}"] = "{{code}}"
        sub_bodyset[f"{ilk}.0.templateList"] = [{"id": "{{assocId}}", **tpl_item}] if tpl_item else []
    steps.append({"method": "POST", "url": cfg["submit_url"], "body_set": sub_bodyset})

    if target == "pending":
        steps.append({"db_wait": {"table": cfg["status_table"], "column": sc,
                                  "where": cfg["parent_where"], "equals": cfg["pending_value"], "timeout_s": 20},
                      "db_capture": {"ver": {"table": cfg["status_table"], "column": vf, "where": cfg["parent_where"]}}})
        return steps

    # ⑤ accept:查 businessKey → BPM 审批 → 等目标态(accept_value)
    steps.append({"db_capture": {"bk": {"table": cfg["bk_table"], "column": cfg["bk_col"],
                                        "where": cfg["bk_where"], "poll_until_nonempty": True, "timeout_s": 24}}})
    bpm = cfg["bpm"]
    steps.append({"method": "GET", "base_url": bpm["base_url"], "session": bpm["session"],
                  "url": bpm["url"], "body": dict(bpm["body"])})
    steps.append({"db_wait": {"table": cfg["status_table"], "column": sc,
                              "where": cfg["parent_where"], "equals": cfg["accept_value"], "timeout_s": 45},
                  "db_capture": {"ver": {"table": cfg["status_table"], "column": vf, "where": cfg["parent_where"]},
                                 "itemId": {"table": cfg["item_table"], "column": cfg.get("item_id_col", "id"), "where": cfg["item_where"]}}})
    return steps

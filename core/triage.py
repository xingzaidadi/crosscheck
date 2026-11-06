"""
失败自动归因(optimization 4):失败用例自动分三桶,减少人判"是 bug 还是我配错"。
  environment  环境/登录/连接/依赖问题 —— 不是功能缺陷,重试或修环境
  modeling     用例/规格配错 —— 断言字段对不上、缺 request/映射、SQL 写错、未人审
  bug_candidate 行为与预期偏差 —— 落库字段不符/计算不变量不符/该拒没拒/状态不对(疑似真缺陷)
纯规则(看 verdict + details 文本),不碰外部;报告按桶聚合,真 bug 候选一眼挑出。
"""
from __future__ import annotations

from core.interfaces import Verdict

_ENV = ("执行异常", "请求异常", "未配可用", "未配写库", "登录", "CAS", "连接", "超时", "ENV", "审批失败", "data_prep 失败")
_MODEL = ("未建模", "缺 request", "缺映射", "缺抓包", "响应字段缺失", "查询失败", "未取到 businessKey",
          "未人审", "缺状态配方", "缺 write", "字段未找到")
_BUG = ("字段不一致", "计算不变量不符", "预期被拒,但响应成功", "行数: 预期", "字段 ", "不一致",
        "事件断言", "只读", "页面值", "幂等失效", "副作用:", "版本冲突")


def classify(verdict, details: list[str]) -> dict:
    """返回 {bucket, reason}。bucket ∈ pass|environment|modeling|bug_candidate|unknown。"""
    if verdict is Verdict.PASS:
        return {"bucket": "pass", "reason": ""}
    if verdict is Verdict.SKIP:
        return {"bucket": "skipped", "reason": (details[0] if details else "")[:60]}
    text = " ".join(details or [])
    if verdict is Verdict.ENV_ERROR or any(k in text for k in _ENV):
        return {"bucket": "environment", "reason": "疑似环境/登录/连接/依赖问题,非功能缺陷"}
    if any(k in text for k in _MODEL):
        return {"bucket": "modeling", "reason": "疑似用例/规格配置问题(断言或字段对不上)"}
    if any(k in text for k in _BUG):
        return {"bucket": "bug_candidate", "reason": "行为与预期偏差,疑似缺陷,建议开发确认"}
    return {"bucket": "unknown", "reason": "未能自动归类,需人工看"}


def summarize(results) -> dict:
    """一批结果按桶计数 + 列出 bug 候选的 case_id。"""
    from collections import Counter
    buckets = Counter()
    bug_ids = []
    for r in results:
        c = classify(r.verdict, r.details)
        buckets[c["bucket"]] += 1
        if c["bucket"] == "bug_candidate":
            bug_ids.append(r.case_id)
    return {"buckets": dict(buckets), "bug_candidates": bug_ids}

"""用例去向(CaseDisposition)一等公民(零业务):把一条用例"最终落在哪、球在谁手里"
的四个面统一成**一个有类型的对象**,而不是散在各处的平行元组/字典:

  state     泛化终态标签(✅PASS / 🔶FAIL / ⛔BLOCKED / ⏳NEEDS_TRIGGER / 🟡PENDING·*)
  owner     该谁补:tool / env / product / defect / ""(已通过)
  need      缺什么 / 怎么补(owner 对应的一句话)
  evidence  证据落点(本次运行目录 / 报告路径;空=尚未跑)

过去 state 在 run_manifest.classify 算、owner/need 在 envneeds.classify_need 算、
evidence 在 CaseResult 里躺,三处各自用 (cid,name,state,...) 元组穿针引线、彼此不认。
现在一处装配:喂 (state, 散文, 证据) → 一个 CaseDisposition,owner/need 由
envneeds 泛化映射填好。各消费者(终态清单 md / 待补清单 md / 报告)读同一对象,不再各自重推。

本模块零业务:state 的业务判定留在 workspace(run_manifest.classify),owner/need 的领域
细化留在 workspace/config(env_needs_rules.yaml);这里只做"把已算好的面装进一等对象"。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CaseDisposition:
    case_id: str
    name: str = ""
    verdict: str = ""              # 原始执行终态 PASS/FAIL/""(未跑出定论)
    state: str = ""                # 泛化终态标签
    why: str = ""                  # state 的一句话解释
    owner: str = ""                # tool/env/product/defect/""(已通过,不入待补清单)
    need: str = ""                 # 缺什么/怎么补
    evidence: str = ""             # 证据落点(运行目录/报告);空=未跑
    blocked_by: list[str] = field(default_factory=list)  # 可选:就绪门禁给的阻塞原因(role/action-body/rule…)

    @property
    def pending(self) -> bool:
        """仍需有人补(未通过且非已检出缺陷之外的待办)——owner 非空即未了结。"""
        return bool(self.owner)


def classify_disposition(case_id: str, name: str, state: str, why: str, prose: str, *,
                         verdict: str = "", evidence: str = "",
                         blocked_by: list[str] | None = None,
                         refine: list[dict] | None = None) -> CaseDisposition:
    """装配一条用例去向:state/why/prose 由上游(业务 classify)给;owner/need 用 envneeds
    泛化映射(+workspace 细化)填;evidence/verdict/blocked_by 有则带上。零业务、纯函数。
    refine=None → 自动加载 workspace 细化规则(与 envneeds.build_env_needs 同契约);
    批量调用应在外层加载一次、显式传入,避免逐条重读。传 [] 则不细化(离线可测)。"""
    from core.envneeds import classify_need, _load_refine
    if refine is None:
        refine = _load_refine()
    r = classify_need(state, prose, refine)
    owner, need = r if r else ("", "")
    return CaseDisposition(
        case_id=case_id, name=name, verdict=verdict, state=state, why=why,
        owner=owner, need=need, evidence=evidence, blocked_by=list(blocked_by or []))


def group_by_owner(disps: list[CaseDisposition]) -> dict[str, list]:
    """按 owner 聚合成 {owner: [(cid, name, need)]},直接喂 envneeds.render_md(签名不变)。
    已通过(owner 为空)的不入清单。"""
    groups: dict[str, list] = {}
    for d in disps:
        if not d.owner:
            continue
        groups.setdefault(d.owner, []).append((d.case_id, d.name, d.need))
    return groups

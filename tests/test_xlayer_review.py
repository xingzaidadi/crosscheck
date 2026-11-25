"""xlayer 档位B 语义复核:字面误报标注 + 快照可复现 + **不动 verdict 铁证**(离线,桩 provider)。

run_tests.py 把每个 test_*.py 当子进程脚本跑(returncode==0 即过),纯 pytest-fixture
风格只 import 不断言=空过;故本文件用 main()+assert+print,run_tests.py 下真执行。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.xlayer_review import (
    STATUS_OK, STATUS_REVIEW, XLAYER_REVIEW,
    freeze_review, review_from_snapshot, review_mismatch,
    review_oracle_result, review_reconcile_result, _snapshot_index,
)


class _StubProvider:
    """离线桩(非真网络):按 field 决定等价与否,记录调用次数。"""

    def __init__(self, equivalent=True, reasons=None):
        self.calls = 0
        self._equivalent = equivalent
        self._reasons = reasons or []

    def __call__(self, **context):
        self.calls += 1
        return {
            "status": STATUS_OK if self._equivalent else STATUS_REVIEW,
            "semantic_equivalent": self._equivalent,
            "tier": "llm",
            "reasons": self._reasons,
        }


class _BoomProvider:
    def __init__(self):
        self.calls = 0

    def __call__(self, **context):
        self.calls += 1
        raise RuntimeError("gateway down")


def _reconcile_payload():
    """枚举码↔中文:字面不等(ok=False),语义其实等价——这正是档位A 的盲区。"""
    return {
        "consistent": False,
        "field_samples": [
            {"pk": "1001", "field": "status", "api": "COMPLETED", "db": "已完成", "ok": False},
            {"pk": "1001", "field": "name", "api": "订单A", "db": "订单A", "ok": True},
        ],
        "field_diffs": ["pk=1001 字段 status: 接口='COMPLETED' vs 库='已完成'"],
    }


def _oracle_payload():
    return {
        "passed": False,
        "results": [
            {"id": "a1", "subject": "api.status", "expected": "已完成",
             "actual": "COMPLETED", "passed": False},
            {"id": "a2", "subject": "api.code", "expected": 200, "actual": 200, "passed": True},
        ],
        "failed": ["a1"],
    }


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    # 1) 档位A 盲区复现:无 llm/snapshot → 字面不等的 status 默认待人审(不臆断等价)。
    base = review_reconcile_result(_reconcile_payload())
    block = base[XLAYER_REVIEW]
    _assert(block["reviewed"] == 1, "只复核 ok==False 的一条(name ok=True 不复核)")
    _assert(block["status"] == STATUS_REVIEW, "档位A 默认待人审")
    _assert(block["tier"] == "lexical", "无 llm/snapshot → tier=lexical")
    _assert(block["reviews"][0]["semantic_equivalent"] is False, "不臆断等价")
    print("[1] 档位A 盲区复现:字面不等默认 needs_human_review,不臆断等价 ✓")

    # 2) 档位B 桩救回:faithful provider → semantic_equivalent + tier=llm。
    prov_ok = _StubProvider(equivalent=True, reasons=["枚举码 COMPLETED 即中文 已完成"])
    live = review_reconcile_result(_reconcile_payload(), llm=prov_ok)
    lblock = live[XLAYER_REVIEW]
    _assert(lblock["status"] == STATUS_OK, "档位B 桩判等价 → semantic_equivalent")
    _assert(lblock["tier"] == "llm", "档位B → tier=llm")
    _assert(lblock["reviews"][0]["semantic_equivalent"] is True, "等价标注")
    _assert(prov_ok.calls == 1, "现复核真调一次 provider")
    print("[2] 档位B 桩救回:枚举码↔中文标为 semantic_equivalent、tier=llm ✓")

    # 3) 快照可复现铁证:freeze → 两次 from_snapshot 逐位一致 + provider 调用计数==0。
    sample = {"pk": "1001", "field": "status", "api": "COMPLETED", "db": "已完成", "ok": False}
    prov_snap = _StubProvider(equivalent=True, reasons=["r"])
    live_one = review_mismatch(sample, llm=prov_snap)
    frozen = freeze_review(live_one["key"], live_one)
    snapshot = {"reviews": [frozen]}
    snap_index = _snapshot_index(snapshot)
    prov_snap.calls = 0   # 清零:判定阶段绝不该再调 provider
    r1 = review_from_snapshot(sample, snap_index)
    r2 = review_from_snapshot(sample, snap_index)
    _assert(r1 == r2, "同一快照两次读回逐位一致(可复现)")
    _assert(r1["status"] == STATUS_OK and r1["tier"] == "llm", "读回保真档位B 结果")
    _assert(prov_snap.calls == 0, "判定只读快照,绝不重调模型")
    # snapshot 优先于 llm(传了 snapshot_index 就不碰 provider)
    prov_boom = _BoomProvider()
    r3 = review_mismatch(sample, llm=prov_boom, snapshot_index=snap_index)
    _assert(r3["status"] == STATUS_OK and prov_boom.calls == 0, "snapshot 优先于 llm,不调模型")
    print("[3] 快照可复现铁证:两次读回逐位一致、provider 调用计数==0、snapshot 优先 ✓")

    # 4) 缺 key 降级:快照里没有该差异 → 确定性 base(tier=lexical,待人审)。
    other = {"pk": "9999", "field": "ghost", "api": "x", "db": "y", "ok": False}
    miss = review_from_snapshot(other, snap_index)
    _assert(miss["tier"] == "lexical" and miss["status"] == STATUS_REVIEW, "缺 key 降级待人审")
    _assert(miss["semantic_equivalent"] is False, "缺 key 不臆断等价")
    print("[4] 快照缺 key 降级:tier=lexical、needs_human_review、不臆断等价 ✓")

    # 4b) 快照保真 tier:档位A base(lexical)冻进快照 → 读回仍 lexical,绝不冒充 llm。
    base_one = review_mismatch(sample)                       # 无 llm/snapshot → lexical base
    frozen_base = freeze_review(base_one["key"], base_one)
    _assert(frozen_base["tier"] == "lexical", "freeze 保真档位A tier=lexical")
    replay_base = review_from_snapshot(sample, _snapshot_index({"reviews": [frozen_base]}))
    _assert(replay_base["tier"] == "lexical", "lexical 快照读回仍 lexical,不冒充 llm")
    _assert(replay_base == base_one, "档位A 快照读回与现判逐位一致(可复现)")
    print("[4b] 快照保真 tier:lexical base 读回仍 lexical,逐位一致 ✓")

    # 5) **不动 verdict 铁证**:复核产物绝不含/不改主判定键。
    recon_in = _reconcile_payload()
    recon_out = review_reconcile_result(recon_in, llm=_StubProvider(equivalent=True))
    _assert("consistent" not in recon_out, "reconcile 复核产物不含 consistent 键")
    _assert(recon_in["consistent"] is False, "原 consistent 未被改动(真不一致仍暴露)")
    oracle_in = _oracle_payload()
    oracle_out = review_oracle_result(oracle_in, llm=_StubProvider(equivalent=True))
    _assert("passed" not in oracle_out, "oracle 复核产物不含 passed 键")
    _assert("failed" not in oracle_out, "oracle 复核产物不含 failed 键")
    _assert(oracle_in["passed"] is False and oracle_in["failed"] == ["a1"],
            "原 passed/failed 未被改动(真不一致仍暴露)")
    ob = oracle_out[XLAYER_REVIEW]
    _assert(ob["reviewed"] == 1 and ob["status"] == STATUS_OK, "oracle 失败项复核为等价候选")
    print("[5] 不动 verdict 铁证:复核产物不含 consistent/passed/failed,主判定逐位不动 ✓")

    # 6) provider 异常降级:_invoke 吞异常 → 确定性 base(不拖垮、不臆断)。
    boom = _BoomProvider()
    degraded = review_mismatch(sample, llm=boom)
    _assert(degraded["tier"] == "lexical", "provider 异常 → 降级 lexical")
    _assert(degraded["status"] == STATUS_REVIEW, "provider 异常 → 待人审")
    _assert(boom.calls == 1, "确实尝试过一次 provider")
    print("[6] provider 异常降级:tier=lexical、needs_human_review、不拖垮主流程 ✓")

    print("\nALL PASS · xlayer 档位B 语义复核(字面误报标注 + 快照可复现 + 不动 verdict)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

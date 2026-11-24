"""
三段式产物报告(通用、零业务、纯渲染)。

扫描 orchestrator 的 run-dir:每条用例目录含
  stage_checkpoint.json  —— 每段 verdict/reasons/attempts/artifact_hash
  artifacts/<stage>.json —— 各段产物
汇总成:
  summarize(run_dir) -> dict(结构化,便于机器消费)
  render_html(summary) -> str(人看的报告)
  write_report(run_dir, out) -> Path(一步到位落 report.html)

只读磁盘、不改判定;报告忠实呈现各段检查点结论与打回原因。
"""
from __future__ import annotations

import html
import json
import os
from pathlib import Path
from typing import Any

from core.stage_contracts import STAGES, StageVerdict


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {}


_IMG_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif")


def _evidence_images(case_dir: Path) -> list[str]:
    """从 actions 产物里抓图类证据路径(绝对路径，去重、保序)。"""
    actions = _read_json(case_dir / "artifacts" / "actions.json").get("actions") or {}
    images: list[str] = []
    seen: set[str] = set()
    for path in actions.get("evidence") or []:
        text = str(path)
        if text.lower().endswith(_IMG_EXT) and text not in seen:
            seen.add(text)
            images.append(text)
    return images


def summarize(run_dir: str | Path) -> dict[str, Any]:
    """扫描 run-dir,汇总每条用例的三段检查点结论。"""
    root = Path(run_dir)
    cases: list[dict[str, Any]] = []
    if root.exists():
        for case_dir in sorted(p for p in root.iterdir() if p.is_dir()):
            checkpoint = _read_json(case_dir / "stage_checkpoint.json")
            if not checkpoint:
                continue
            stages: list[dict[str, Any]] = []
            for stage in STAGES:
                info = checkpoint.get(stage) or {}
                stages.append({
                    "stage": stage,
                    "verdict": info.get("verdict", "not_run"),
                    "reasons": info.get("reasons") or [],
                    "attempts": info.get("attempts", 0),
                    "artifact_hash": (info.get("artifact_hash") or "")[:12],
                })
            passed = [s for s in stages if s["verdict"] == StageVerdict.PASS.value]
            completed = len(passed) == len(STAGES)
            stopped_at = ""
            if not completed:
                for s in stages:
                    if s["verdict"] != StageVerdict.PASS.value:
                        stopped_at = s["stage"]
                        break
            cases.append({
                "case_id": case_dir.name,
                "completed": completed,
                "stopped_at": stopped_at,
                "stages": stages,
                "evidence_images": _evidence_images(case_dir),
            })
    totals = {
        "cases": len(cases),
        "completed": sum(1 for c in cases if c["completed"]),
        "stopped": sum(1 for c in cases if not c["completed"]),
        "by_stage": {stage: {"pass": 0, "reject": 0, "not_run": 0} for stage in STAGES},
    }
    for case in cases:
        for stage_info in case["stages"]:
            bucket = totals["by_stage"][stage_info["stage"]]
            key = stage_info["verdict"] if stage_info["verdict"] in bucket else "not_run"
            bucket[key] += 1
    return {"run_dir": str(root), "totals": totals, "cases": cases}


_STAGE_TITLE = {"spec": "① 用例转操作", "actions": "② UI 操作", "evidence": "③ 操作后验证"}
_BADGE = {"pass": ("✔", "#1a7f37", "#dafbe1"),
          "reject": ("✘", "#cf222e", "#ffebe9"),
          "not_run": ("·", "#6e7781", "#eef1f4")}


def _badge(verdict: str) -> str:
    mark, fg, bg = _BADGE.get(verdict, _BADGE["not_run"])
    return (f"<span style='display:inline-block;min-width:18px;text-align:center;"
            f"border-radius:4px;padding:1px 6px;color:{fg};background:{bg};"
            f"font-weight:600'>{mark} {html.escape(verdict)}</span>")


def _thumbs(images: list[str]) -> str:
    """渲染可点击缩略图条(file:// 链接，点击看大图)。"""
    if not images:
        return ""
    cells = []
    for path in images:
        uri = Path(path).as_uri() if os.path.isabs(path) else html.escape(path)
        safe = html.escape(path)
        cells.append(
            f"<a href='{uri}' target='_blank' title='{safe}'>"
            f"<img src='{uri}' style='height:56px;border:1px solid #d0d7de;"
            f"border-radius:4px;margin:2px;object-fit:cover'></a>")
    return ("<div style='margin-top:6px;display:flex;flex-wrap:wrap;gap:2px'>"
            + "".join(cells) + "</div>")


def render_html(summary: dict[str, Any]) -> str:
    totals = summary["totals"]
    stage_heads = "".join(f"<th>{html.escape(_STAGE_TITLE.get(s, s))}</th>" for s in STAGES)

    rows = []
    for case in summary["cases"]:
        cells = [f"<td><b>{html.escape(case['case_id'])}</b></td>"]
        for stage_info in case["stages"]:
            reasons = stage_info["reasons"]
            reason_html = ""
            if reasons:
                items = "".join(f"<li>{html.escape(str(r))}</li>" for r in reasons)
                reason_html = (f"<ul style='margin:4px 0 0;padding-left:16px;color:#57606a;"
                               f"font-size:12px'>{items}</ul>")
            attempts = stage_info["attempts"]
            meta = (f"<div style='color:#8c959f;font-size:11px;margin-top:2px'>"
                    f"attempts={attempts} · {html.escape(stage_info['artifact_hash'])}</div>")
            cells.append(f"<td style='vertical-align:top'>{_badge(stage_info['verdict'])}"
                         f"{meta}{reason_html}</td>")
        status = ("<span style='color:#1a7f37'>完成</span>" if case["completed"]
                  else f"<span style='color:#cf222e'>停在 {html.escape(case['stopped_at'])}</span>")
        cells.append(f"<td>{status}</td>")
        cells.append(f"<td>{_thumbs(case.get('evidence_images') or [])}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")

    by_stage = totals["by_stage"]
    stage_cards = "".join(
        f"<div style='border:1px solid #d0d7de;border-radius:8px;padding:10px 14px'>"
        f"<div style='font-weight:600'>{html.escape(_STAGE_TITLE.get(s, s))}</div>"
        f"<div style='color:#57606a;font-size:13px'>过闸 {by_stage[s]['pass']} · "
        f"打回 {by_stage[s]['reject']} · 未跑 {by_stage[s]['not_run']}</div></div>"
        for s in STAGES)

    return f"""<!doctype html><html lang=zh><head><meta charset=utf-8>
<title>三段式流水线报告</title>
<style>
 body{{font:14px/1.6 "Segoe UI","Microsoft YaHei",Arial;margin:24px;color:#1f2328;background:#f6f8fa}}
 h1{{font-size:20px;margin:0 0 4px}} .sub{{color:#57606a;margin-bottom:16px}}
 .cards{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:18px}}
 table{{border-collapse:collapse;width:100%;background:#fff;border:1px solid #d0d7de;border-radius:8px;overflow:hidden}}
 th,td{{border-bottom:1px solid #eaeef2;padding:8px 12px;text-align:left}}
 th{{background:#f6f8fa;font-size:13px}}
</style></head><body>
<h1>三段式流水线报告</h1>
<div class=sub>{html.escape(summary['run_dir'])} · 用例 {totals['cases']} · 完成 {totals['completed']} · 打回/停 {totals['stopped']}</div>
<div class=cards>{stage_cards}</div>
<table><tr><th>用例</th>{stage_heads}<th>结论</th><th>UI 证据</th></tr>{''.join(rows)}</table>
</body></html>"""


def write_report(run_dir: str | Path, out: str | Path | None = None) -> Path:
    """汇总 run-dir 并落 report.html。out 默认 <run_dir>/report.html。"""
    summary = summarize(run_dir)
    target = Path(out) if out else (Path(run_dir) / "report.html")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_html(summary), encoding="utf-8")
    (target.parent / "report.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return target

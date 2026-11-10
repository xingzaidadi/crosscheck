"""
富测试报告渲染:一次运行一个文件夹,report.html 详列每条用例的
  做了什么 / 预期 / 实际 / 查了哪些库表 / 执行的 SQL / 数据样本 / 逐字段对比 / 截图 + 录像。

CaseResult.report 的结构(由各执行器填充):
  {
    "did": [str],                      # 做了什么(有序步骤)
    "layers": [                        # 各校验层
      {"name","ok","expected","actual","tables":[str],"sql":str,"note":str,
       "cols":[str],"rows":[[cell...]]}  # 可选:逐条/逐字段明细表(最后一列渲染为 ✓/✗)
    ],
    "evidence": {"screenshots":[相对路径], "video":相对路径}
  }
"""
from __future__ import annotations

import html
import json
import time
from pathlib import Path

from core.interfaces import CaseResult, Verdict

_LABEL = {Verdict.PASS: "通过", Verdict.FAIL: "失败", Verdict.ENV_ERROR: "环境错",
          Verdict.ABORTED: "作废", Verdict.SKIP: "跳过"}
_COLOR = {Verdict.PASS: "#1a7f37", Verdict.FAIL: "#cf222e", Verdict.ENV_ERROR: "#9a6700",
          Verdict.ABORTED: "#8250df", Verdict.SKIP: "#57606a"}


def _esc(v) -> str:
    return html.escape("" if v is None else str(v))


def _detail_table(cols, rows) -> str:
    if not cols:
        return ""
    head = "".join(f"<th>{_esc(c)}</th>" for c in cols)
    body = []
    for r in rows:
        tds = "".join(f"<td>{_esc(c)}</td>" for c in r)
        body.append(f"<tr>{tds}</tr>")
    return f"<table class=dt><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def _layer_html(ly: dict) -> str:
    ok = ly.get("ok")
    badge = "<span class='ok'>一致 ✓</span>" if ok else "<span class='bad'>不一致 ✗</span>"
    parts = [f"<div class=layer><div class=lh><b>{_esc(ly.get('name'))}</b> {badge}</div>"]
    if ly.get("expected") is not None:
        parts.append(f"<div class=kv><span>预期</span>{_esc(ly['expected'])}</div>")
    if ly.get("actual") is not None:
        parts.append(f"<div class=kv><span>实际</span>{_esc(ly['actual'])}</div>")
    if ly.get("tables"):
        parts.append(f"<div class=kv><span>查的库表</span>{_esc('、'.join(ly['tables']))}</div>")
    if ly.get("sql"):
        parts.append(f"<div class=kv><span>SQL</span><code>{_esc(ly['sql'])}</code></div>")
    if ly.get("note"):
        parts.append(f"<div class=note>{_esc(ly['note'])}</div>")
    if ly.get("cols"):
        parts.append(_detail_table(ly["cols"], ly.get("rows", [])))
    parts.append("</div>")
    return "".join(parts)


def _evidence_html(ev: dict, run_dir: Path) -> str:
    if not ev:
        return ""
    out = ["<div class=evi><b>证据</b>"]
    for s in ev.get("screenshots", []):
        out.append(f"<div><a href='{_esc(s)}'>{_esc(s)}</a><br>"
                   f"<img src='{_esc(s)}' style='max-width:520px;border:1px solid #d0d7de'></div>")
    if ev.get("video"):
        v = ev["video"]
        out.append(f"<div><a href='{_esc(v)}'>操作录像 {_esc(v)}</a><br>"
                   f"<video controls width='520' src='{_esc(v)}'></video></div>")
    for d in ev.get("data", []):
        out.append(f"<div><a href='{_esc(d)}'>{_esc(d)}</a></div>")
    out.append("</div>")
    return "".join(out)


def reconcile_layer(rec, mapping: dict) -> dict:
    """ReconcileResult + mapping → 报告层(查的表/SQL/接口vs库/字段样本)。"""
    tables = [mapping.get("table")] + [j.get("table") for j in (mapping.get("joins") or [])]
    cols = ["主键", "字段(库列)", "接口值", "库值", "一致"]
    rows = [[s["pk"], s["field"], s["api"], s["db"], "✓" if s["ok"] else "✗"]
            for s in rec.field_samples]
    act = []
    if rec.api_total is not None or rec.db_total is not None:
        act.append(f"接口总数={rec.api_total} · 库 COUNT(DISTINCT)={rec.db_total}")
    act.append(f"字段抽样 {len(rec.field_samples)} 项")
    return {"name": "接口 ↔ 库 对账", "ok": rec.consistent,
            "expected": "接口总数 == 库去重计数;抽样行逐字段相等",
            "actual": " · ".join(act),
            "tables": [t for t in tables if t], "sql": rec.count_sql or rec.where_sql,
            "cols": cols, "rows": rows}


def ui_layer(ui) -> dict:
    """UiResult → 报告层(逐行逐字段 页面 vs 接口)。"""
    cols = ["行", "字段", "页面显示", "接口值", "一致"]
    rows = [[p["row"], p["field"], p["page"], p["api"], "✓" if p["ok"] else "✗"] for p in ui.pairs]
    return {"name": "页面 ↔ 接口 渲染校验", "ok": ui.consistent,
            "expected": "页面每行每字段显示 == 接口返回",
            "actual": f"比对 {ui.checked_rows} 行 × {len(set(p['field'] for p in ui.pairs))} 字段",
            "cols": cols, "rows": rows}


def render(run_id: str, results: list[CaseResult], run_dir: Path) -> Path:
    cards = []
    for r in results:
        rep = r.report or {}
        color = _COLOR.get(r.verdict, "#57606a")
        label = _LABEL.get(r.verdict, r.verdict.value)
        did = "".join(f"<li>{_esc(x)}</li>" for x in rep.get("did", []))
        layers = "".join(_layer_html(ly) for ly in rep.get("layers", []))
        # 没有结构化 report 时,退回展示 details 文本
        if not rep:
            layers = "<div class=layer>" + "<br>".join(_esc(d) for d in r.details) + "</div>"
        evi = _evidence_html(rep.get("evidence", {}), run_dir)
        fid = r.fidelity or {}
        if fid.get("score") is not None:
            g = fid.get("grade", ""); sc = fid.get("score")
            gcolor = {"A": "#1a7f37", "B": "#2da44e", "C": "#bf8700", "D": "#cf222e"}.get(g, "#57606a")
            av = f" · {_esc(r.act_via)}" if r.act_via else ""
            score_chip = f"<span class=badge style='background:{gcolor}' title='走单对账保真度'>走单 {sc}/100 {_esc(g)}{av}</span>"
        else:
            score_chip = ""
        cards.append(f"""
<section class=case>
  <h2><span class=badge style='background:{color}'>{label}</span>
      {score_chip}
      {_esc(r.case_id)} <span class=title>{_esc(r.title)}</span>
      <span class=meta>{_esc(r.kind)}/{_esc(r.mode)} · {r.duration_s}s</span></h2>
  {'<div class=did><b>做了什么</b><ol>'+did+'</ol></div>' if did else ''}
  {layers}
  {evi}
</section>""")

    n = len(results)
    npass = sum(1 for r in results if r.verdict is Verdict.PASS)
    nfail = sum(1 for r in results if r.verdict is Verdict.FAIL)
    nskip = sum(1 for r in results if r.verdict is Verdict.SKIP)
    doc = f"""<!doctype html><html lang=zh><head><meta charset=utf-8><title>测试报告 {run_id}</title>
<style>
body{{font:14px/1.7 -apple-system,Segoe UI,Arial,sans-serif;margin:0;background:#f6f8fa;color:#1f2328}}
header{{background:#24292f;color:#fff;padding:16px 28px}}
header .s{{font-size:13px;color:#c9d1d9;margin-top:6px}}
main{{max-width:980px;margin:0 auto;padding:20px}}
.case{{background:#fff;border:1px solid #d0d7de;border-radius:10px;padding:16px 20px;margin:16px 0}}
.case h2{{font-size:16px;margin:0 0 10px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}}
.badge{{color:#fff;border-radius:6px;padding:2px 10px;font-size:13px}}
.title{{font-weight:400;color:#57606a}}
.meta{{margin-left:auto;font-size:12px;color:#8c959f;font-weight:400}}
.did ol{{margin:6px 0 12px;padding-left:22px}}
.layer{{border:1px solid #e4e8ec;border-radius:8px;padding:10px 12px;margin:10px 0;background:#fbfcfd}}
.lh{{margin-bottom:6px}}
.ok{{color:#1a7f37;font-weight:600}} .bad{{color:#cf222e;font-weight:600}}
.kv{{margin:3px 0}} .kv>span{{display:inline-block;min-width:76px;color:#57606a}}
.kv code{{background:#eef1f4;padding:2px 6px;border-radius:5px;font-size:12px;word-break:break-all}}
.note{{color:#8c959f;font-size:12px;margin:4px 0}}
table.dt{{border-collapse:collapse;margin:8px 0;width:100%;font-size:13px}}
table.dt th,table.dt td{{border:1px solid #d9dee3;padding:4px 8px;text-align:left}}
table.dt th{{background:#f0f3f6}}
.evi{{margin-top:10px}} .evi>div{{margin:8px 0}}
</style></head><body>
<header><div style='font-size:18px;font-weight:600'>测试报告</div>
<div class=s>运行 {run_id} · 共 {n} · <b style='color:#7ee787'>通过 {npass}</b> · <b style='color:#ff7b72'>失败 {nfail}</b> · 跳过 {nskip} · 生成 {time.strftime('%Y-%m-%d %H:%M:%S')}</div></header>
<main>{''.join(cards)}</main></body></html>"""
    out = run_dir / "report.html"
    out.write_text(doc, encoding="utf-8")
    # 机器可读小结:供跨运行总览(render_index)聚合
    (run_dir / "summary.json").write_text(json.dumps({
        "run_id": run_id, "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total": n, "pass": npass, "fail": nfail, "skip": nskip,
        "env_error": sum(1 for r in results if r.verdict is Verdict.ENV_ERROR),
        "cases": [{"case_id": r.case_id, "title": r.title, "verdict": r.verdict.value,
                   "kind": r.kind, "mode": r.mode, "duration_s": r.duration_s,
                   "score": (r.fidelity or {}).get("score"), "grade": (r.fidelity or {}).get("grade"),
                   "act_via": r.act_via, "ui_triggered": r.ui_triggered,
                   "note": (r.details[0] if r.details else "")} for r in results],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def render_index(runs_root: Path) -> Path | None:
    """扫 runs_root 下各次运行的 summary.json,出一页总览 index.html:历次通过率 + 直达各报告。"""
    runs_root = Path(runs_root)
    rows, pts = [], []
    for d in sorted(runs_root.glob("run_*"), reverse=True):
        sj = d / "summary.json"
        if not sj.exists():
            continue
        try:
            s = json.loads(sj.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        tot, pz, fl = s.get("total", 0), s.get("pass", 0), s.get("fail", 0)
        rate = (pz / tot * 100) if tot else 0
        pts.append(rate)
        rows.append(
            f"<tr><td><a href='{_esc(d.name)}/report.html'>{_esc(d.name)}</a></td>"
            f"<td>{_esc(s.get('generated_at',''))}</td><td>{tot}</td>"
            f"<td class=p>{pz}</td><td class=f>{fl}</td><td>{s.get('skip',0)}</td>"
            f"<td><b>{rate:.0f}%</b></td></tr>")
    if not rows:
        return None
    # 通过率趋势(老→新)做个极简 sparkline 条
    spark = "".join(
        f"<span title='{v:.0f}%' style='display:inline-block;width:8px;margin-right:2px;"
        f"height:{max(3,int(v*0.4))}px;background:{'#1a7f37' if v>=99 else '#9a6700' if v>=50 else '#cf222e'};"
        f"vertical-align:bottom'></span>" for v in reversed(pts))
    doc = f"""<!doctype html><html lang=zh><head><meta charset=utf-8><title>crosscheck 运行总览</title>
<style>
body{{font:14px/1.7 -apple-system,Segoe UI,Arial,sans-serif;margin:0;background:#f6f8fa;color:#1f2328}}
header{{background:#24292f;color:#fff;padding:16px 28px}}
main{{max-width:900px;margin:0 auto;padding:20px}}
table{{border-collapse:collapse;width:100%;background:#fff;border:1px solid #d0d7de;border-radius:8px;overflow:hidden}}
th,td{{border-bottom:1px solid #eaecef;padding:8px 12px;text-align:left;font-size:13px}}
th{{background:#f0f3f6}} td.p{{color:#1a7f37;font-weight:600}} td.f{{color:#cf222e;font-weight:600}}
.spark{{background:#fff;border:1px solid #d0d7de;border-radius:8px;padding:14px;margin:0 0 16px}}
</style></head><body>
<header><div style='font-size:18px;font-weight:600'>crosscheck 运行总览</div>
<div style='font-size:13px;color:#c9d1d9;margin-top:6px'>共 {len(rows)} 次运行 · 生成 {time.strftime('%Y-%m-%d %H:%M:%S')}</div></header>
<main>
<div class=spark><b>通过率趋势</b>(老 → 新)<div style='margin-top:8px;height:44px'>{spark}</div></div>
<table><thead><tr><th>运行</th><th>时间</th><th>共</th><th>通过</th><th>失败</th><th>跳过</th><th>通过率</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
</main></body></html>"""
    out = runs_root / "index.html"
    out.write_text(doc, encoding="utf-8")
    return out

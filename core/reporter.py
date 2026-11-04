"""报告:汇总每条用例的判定,输出人能读的控制台文本 + 一页 HTML。"""
from __future__ import annotations

import html
import time
from pathlib import Path

from .interfaces import CaseResult, Verdict

_LABEL = {
    Verdict.PASS: "通过", Verdict.FAIL: "失败", Verdict.ENV_ERROR: "环境错",
    Verdict.ABORTED: "作废", Verdict.SKIP: "跳过",
}
_COLOR = {
    Verdict.PASS: "#1a7f37", Verdict.FAIL: "#cf222e", Verdict.ENV_ERROR: "#9a6700",
    Verdict.ABORTED: "#8250df", Verdict.SKIP: "#57606a",
}


class Reporter:
    def __init__(self):
        self.results: list[CaseResult] = []

    def add(self, result: CaseResult) -> None:
        self.results.append(result)

    def summary(self) -> dict:
        by = {v: 0 for v in Verdict}
        for r in self.results:
            by[r.verdict] += 1
        return {
            "total": len(self.results),
            "pass": by[Verdict.PASS],
            "fail": by[Verdict.FAIL],
            "env_error": by[Verdict.ENV_ERROR],
            "aborted": by[Verdict.ABORTED],
            "skip": by[Verdict.SKIP],
            "cleanup_failed": sum(1 for r in self.results if not r.cleanup_ok),
        }

    def render(self) -> str:
        """控制台文本报告。"""
        lines = ["=== 批量测试报告 ==="]
        for r in self.results:
            label = _LABEL.get(r.verdict, r.verdict.value)
            head = f"[{label:4}] {r.case_id}"
            if r.title:
                head += f"  {r.title}"
            head += f"  ({r.duration_s}s)"
            lines.append(head)
            for d in r.details:
                lines.append(f"      - {d}")
            if not r.cleanup_ok:
                lines.append("      ! 清理未完成(已标 cleanup_pending)")
        s = self.summary()
        lines.append(
            f"\n小结: 共 {s['total']} · 通过 {s['pass']} · 失败 {s['fail']} · "
            f"环境错 {s['env_error']} · 作废 {s['aborted']} · 跳过 {s['skip']}")
        return "\n".join(lines)

    def to_html(self, path: str | Path) -> Path:
        """一页 HTML 汇总报告。"""
        s = self.summary()
        rows = []
        for r in self.results:
            color = _COLOR.get(r.verdict, "#57606a")
            label = _LABEL.get(r.verdict, r.verdict.value)
            details = "<br>".join(html.escape(d) for d in r.details) or "—"
            rows.append(
                f"<tr><td>{html.escape(r.case_id)}</td>"
                f"<td>{html.escape(r.title)}</td>"
                f"<td>{html.escape(r.kind)}/{html.escape(r.mode)}</td>"
                f"<td style='color:{color};font-weight:600'>{label}</td>"
                f"<td>{details}</td>"
                f"<td style='text-align:right'>{r.duration_s}s</td></tr>")
        doc = f"""<!doctype html><html lang=zh><head><meta charset=utf-8>
<title>批量测试报告</title>
<style>
body{{font:14px/1.6 -apple-system,Segoe UI,Arial,sans-serif;margin:24px;color:#1f2328}}
h1{{font-size:20px}}
.sum{{margin:12px 0;padding:10px 14px;background:#f6f8fa;border-radius:8px}}
.sum b{{font-size:18px}}
table{{border-collapse:collapse;width:100%;margin-top:12px}}
th,td{{border:1px solid #d0d7de;padding:6px 10px;vertical-align:top;text-align:left}}
th{{background:#f6f8fa}}
</style></head><body>
<h1>批量测试报告</h1>
<div class=sum>共 <b>{s['total']}</b> · 通过 <b style='color:#1a7f37'>{s['pass']}</b>
 · 失败 <b style='color:#cf222e'>{s['fail']}</b> · 环境错 {s['env_error']}
 · 作废 {s['aborted']} · 跳过 {s['skip']} &nbsp;|&nbsp; 生成 {time.strftime('%Y-%m-%d %H:%M:%S')}</div>
<table><thead><tr><th>用例</th><th>标题</th><th>类型/方式</th><th>结论</th><th>说明</th><th>耗时</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
</body></html>"""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(doc, encoding="utf-8")
        return p

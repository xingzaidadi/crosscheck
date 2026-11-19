"""Read-only local control-plane snapshot and dashboard."""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from core.knowledge import KnowledgeBase


def snapshot(workspace: str | Path) -> dict[str, Any]:
    root = Path(workspace).resolve()
    profiles = sorted(path.stem for path in (root / "profiles").glob("*.yaml") if not path.name.startswith("_"))
    suites = []
    for directory in sorted((root / "suites").glob("*")):
        if not directory.is_dir():
            continue
        score_path = directory / "suite_score.json"
        score = {}
        if score_path.is_file():
            try:
                score = json.loads(score_path.read_text(encoding="utf-8"))
            except ValueError:
                pass
        suites.append({"suite_id": directory.name, "total": score.get("total"),
                       "ready": score.get("execution_ready", score.get("ready")),
                       "score": score.get("average_score")})
    runs = []
    for path in sorted((root / "runs").glob("*/summary.json"), reverse=True)[:30]:
        try:
            summary = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        runs.append({"run_id": path.parent.name, "total": summary.get("total", 0),
                     "pass": summary.get("pass", 0), "fail": summary.get("fail", 0),
                     "blocked": summary.get("blocked", 0)})
    knowledge = KnowledgeBase(root).load()
    capabilities = []
    capability_path = root / "capabilities.yaml"
    if capability_path.is_file():
        try:
            from core.arsenal import load_capabilities
            capabilities = [{"ref": item.ref, "state": item.state.value,
                             "environment": item.environment,
                             "success_rate": item.success_rate}
                            for item in load_capabilities(capability_path)]
        except Exception:
            capabilities = []
    return {"workspace": str(root), "profiles": profiles, "suites": suites, "runs": runs,
            "capabilities": capabilities,
            "knowledge": {"total": len(knowledge.records()),
                          "pending": len(knowledge.records(status="pending")),
                          "conflicts": len(knowledge.conflicts())}}


def render_dashboard(workspace: str | Path, output: str | Path | None = None) -> Path:
    data = snapshot(workspace)
    root = Path(workspace).resolve()
    output_path = Path(output).resolve() if output else root / "dashboard.html"
    suite_rows = "".join(f"<tr><td>{html.escape(str(item['suite_id']))}</td><td>{item['total']}</td>"
                         f"<td>{item['ready']}</td><td>{item['score']}</td></tr>" for item in data["suites"])
    run_rows = "".join(f"<tr><td>{html.escape(str(item['run_id']))}</td><td>{item['total']}</td>"
                       f"<td>{item['pass']}</td><td>{item['fail']}</td><td>{item['blocked']}</td></tr>"
                       for item in data["runs"])
    document = f"""<!doctype html><html lang=zh><head><meta charset=utf-8><title>Crosscheck</title>
<style>body{{font:14px/1.6 Segoe UI,Arial;margin:24px;color:#1f2328}} .cards{{display:flex;gap:12px}}
.card{{padding:14px 18px;background:#f6f8fa;border-radius:8px;min-width:120px}} table{{border-collapse:collapse;width:100%;margin:12px 0 24px}}
th,td{{border:1px solid #d0d7de;padding:7px 10px;text-align:left}} th{{background:#f6f8fa}}</style></head><body>
<h1>Crosscheck 控制台</h1><div>{html.escape(data['workspace'])}</div><div class=cards>
<div class=card>Profiles<br><b>{len(data['profiles'])}</b></div><div class=card>Suites<br><b>{len(data['suites'])}</b></div>
<div class=card>Knowledge<br><b>{data['knowledge']['total']}</b></div><div class=card>Pending<br><b>{data['knowledge']['pending']}</b></div>
<div class=card>Conflicts<br><b>{data['knowledge']['conflicts']}</b></div></div>
<h2>套件</h2><table><tr><th>Suite</th><th>Total</th><th>READY</th><th>Score</th></tr>{suite_rows}</table>
<h2>最近运行</h2><table><tr><th>Run</th><th>Total</th><th>Pass</th><th>Fail</th><th>Blocked</th></tr>{run_rows}</table>
<h2>能力</h2><table><tr><th>Capability</th><th>State</th><th>Environment</th><th>Success rate</th></tr>{''.join(f"<tr><td>{html.escape(str(item['ref']))}</td><td>{item['state']}</td><td>{html.escape(str(item['environment']))}</td><td>{item['success_rate']}</td></tr>" for item in data['capabilities'])}</table>
</body></html>"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(document, encoding="utf-8")
    return output_path

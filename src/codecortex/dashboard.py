"""Read-only local observability dashboard for CodeCortex."""

from __future__ import annotations

import asyncio
import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from codecortex.architecture import ArchitectureDriftDetector, ArchitectureFingerprint
from codecortex.dependencies import DependencyIntelligence
from codecortex.evaluation import BenchmarkHistory
from codecortex.indexing.incremental_graph import IncrementalGraphIndex
from codecortex.pr_intelligence import PRIntelligence
from codecortex.precision import PrecisionEvidenceProvider
from codecortex.runtime import CortexRuntime
from codecortex.structural import StructuralSearch
from codecortex.tracing import TaskTraceRecorder

_SAFE_REF = re.compile(r"^[A-Za-z0-9._/@+-]{1,200}$")


def _read_events(runtime: CortexRuntime, limit: int = 10_000) -> list[dict[str, Any]]:
    path = runtime.config.state_dir / "runtime" / "events.jsonl"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    except OSError:
        return []
    events: list[dict[str, Any]] = []
    for line in lines:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            events.append(payload)
    return events


def _event_stats(events: list[dict[str, Any]]) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    routes: Counter[str] = Counter()
    token_saved = 0
    engine_ms: defaultdict[str, float] = defaultdict(float)
    engine_calls: Counter[str] = Counter()
    for event in events:
        name = str(event.get("name", "unknown"))
        raw_attrs = event.get("attributes")
        attrs: dict[str, Any] = raw_attrs if isinstance(raw_attrs, dict) else {}
        counts[name] += 1
        if name == "route.created":
            routes[str(attrs.get("kind", "unknown"))] += 1
        elif name == "context.fitted":
            token_saved += int(attrs.get("saved", 0) or 0)
        elif name == "engine.executed":
            capability = str(attrs.get("capability", "unknown"))
            engine_calls[capability] += 1
            engine_ms[capability] += float(attrs.get("duration_ms", 0.0) or 0.0)
    engine_latency = {
        key: round(engine_ms[key] / count, 2)
        for key, count in engine_calls.items()
        if count
    }
    return {
        "counts": dict(counts),
        "routes": dict(routes),
        "context_tokens_saved": token_saved,
        "engine_avg_latency_ms": engine_latency,
    }


def _recent_traces(runtime: CortexRuntime, limit: int = 12) -> list[dict[str, Any]]:
    recorder = TaskTraceRecorder(runtime.config.state_dir / "runtime" / "traces.jsonl")
    spans = recorder.read(limit=2_000)
    trace_ids: list[str] = []
    for span in reversed(spans):
        if span.trace_id not in trace_ids:
            trace_ids.append(span.trace_id)
        if len(trace_ids) >= limit:
            break
    result: list[dict[str, Any]] = []
    for trace_id in trace_ids:
        try:
            result.append(asdict(recorder.summarize(trace_id)))
        except (KeyError, ValueError):
            continue
    return result


def _benchmark_history(runtime: CortexRuntime, limit: int = 12) -> list[dict[str, Any]]:
    history = BenchmarkHistory(runtime.config.state_dir / "benchmarks" / "history.json").load()
    return [asdict(item) for item in history[-limit:]]


def _architecture_drift(runtime: CortexRuntime, graph: Any) -> dict[str, Any]:
    detector = ArchitectureDriftDetector()
    current = detector.fingerprint(graph)
    target = runtime.config.state_dir / "architecture" / "baseline.json"
    baseline = ArchitectureFingerprint.load(target)
    if baseline is None:
        return {"status": "no-baseline", "current": asdict(current)}
    report = detector.compare(baseline, current)
    return {"status": "compared", "report": asdict(report)}


def _evidence_layers(runtime: CortexRuntime, events: list[dict[str, Any]]) -> dict[str, Any]:
    """Report capability state for the optional evidence layers.

    Labels are CodeCortex-native; nothing here names an upstream project.
    """
    root = runtime.config.project_root
    precision = PrecisionEvidenceProvider(root, runtime.config).status()
    dependencies = DependencyIntelligence(root, runtime.config).status()
    structural = StructuralSearch(root, runtime.config).status()
    rewrites = [
        event
        for event in events
        if event.get("name") == "structural.rewrite.applied"
    ]
    applied = sum(1 for event in rewrites if event.get("attributes", {}).get("applied"))
    return {
        "precision": {
            "status": precision.label,
            "documents": precision.documents,
            "symbols": precision.symbols,
            "occurrences": precision.occurrences,
            "stale": precision.stale,
            "detail": precision.stale_reason or precision.detail,
        },
        "dependencies": {
            "status": dependencies.label,
            "cache_writable": dependencies.cache_writable,
            "detail": dependencies.detail,
        },
        "structural": {
            "status": structural.label,
            "version": structural.version,
            "detail": structural.detail,
            "rewrites_applied": applied,
            "rewrites_failed": len(rewrites) - applied,
        },
    }


async def _overview(runtime: CortexRuntime) -> dict[str, Any]:
    graph, index_stats = await asyncio.to_thread(
        IncrementalGraphIndex(runtime.config.project_root).refresh
    )
    health = await runtime.gateway.health()
    events = _read_events(runtime)
    stats = _event_stats(events)
    degree: Counter[str] = Counter()
    for edge in graph.edges:
        degree[edge.source] += 1
        degree[edge.target] += 1
    by_id = {node.id: node for node in graph.nodes}
    hot_nodes = [
        {
            "id": node_id,
            "name": by_id[node_id].name if node_id in by_id else node_id,
            "path": by_id[node_id].path if node_id in by_id else None,
            "degree": count,
        }
        for node_id, count in degree.most_common(12)
    ]
    return {
        "project": str(runtime.config.project_root),
        "active_backends": list(runtime.active_backends),
        "health": health,
        "index": {
            "tracked": index_stats.index.tracked,
            "files_reparsed": index_stats.files_reparsed,
            "full_rebuild": index_stats.full_rebuild,
            "duration_ms": index_stats.index.duration_ms,
        },
        "graph": {
            "nodes": len(graph.nodes),
            "edges": len(graph.edges),
            "counts": graph.counts(),
            "hot_nodes": hot_nodes,
        },
        "runtime": stats,
        "traces": _recent_traces(runtime),
        "benchmarks": _benchmark_history(runtime),
        "architecture": _architecture_drift(runtime, graph),
        "evidence": await asyncio.to_thread(_evidence_layers, runtime, events),
    }


def _html(project: str) -> str:
    escaped = (
        project.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark">
<title>CodeCortex Observatory</title>
<style>
:root{{--bg:#090b0f;--panel:#11151b;--line:#252c36;--muted:#8b96a5;--text:#f4f7fb;--accent:#8ce0c8;--warn:#f3c969}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 ui-sans-serif,system-ui,-apple-system,sans-serif}}
main{{max-width:1280px;margin:auto;padding:32px}}header{{display:flex;justify-content:space-between;gap:24px;align-items:end;margin-bottom:24px}}
h1{{font-size:34px;margin:0}}.muted{{color:var(--muted)}}code{{font-family:ui-monospace,SFMono-Regular,monospace}}
.grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}}.card,.panel{{border:1px solid var(--line);background:var(--panel);border-radius:14px;padding:16px}}
.metric{{font-size:28px;font-weight:700;margin-top:5px}}.wide{{grid-column:span 2}}.full{{grid-column:1/-1}}
section{{margin-top:12px}}h2{{font-size:16px;margin:0 0 12px}}table{{width:100%;border-collapse:collapse}}th,td{{text-align:left;border-bottom:1px solid var(--line);padding:8px 4px}}th{{color:var(--muted);font-weight:500}}
.pill{{display:inline-block;border:1px solid var(--line);border-radius:999px;padding:2px 8px;margin:2px}}.ok{{color:var(--accent)}}.bad{{color:var(--warn)}}
.bar{{height:7px;background:#202630;border-radius:9px;overflow:hidden;margin-top:5px}}.bar>i{{display:block;height:100%;background:var(--accent)}}
@media(max-width:850px){{.grid{{grid-template-columns:1fr 1fr}}.wide{{grid-column:1/-1}}}}@media(max-width:520px){{main{{padding:18px}}.grid{{grid-template-columns:1fr}}.wide{{grid-column:auto}}header{{display:block}}}}
</style>
</head><body><main>
<header><div><h1>CodeCortex Observatory</h1><div class="muted"><code>{escaped}</code></div></div><div id="updated" class="muted">Loading…</div></header>
<div id="metrics" class="grid"></div>
<section class="grid">
<div class="panel wide"><h2>Backend health</h2><div id="health"></div></div>
<div class="panel wide"><h2>Routing distribution</h2><div id="routes"></div></div>
<div class="panel wide"><h2>Hot graph nodes</h2><table><thead><tr><th>Node</th><th>Path</th><th>Degree</th></tr></thead><tbody id="hot"></tbody></table></div>
<div class="panel wide"><h2>Recent traces</h2><table><thead><tr><th>Trace</th><th>Spans</th><th>ms</th><th>Tokens</th><th>Errors</th></tr></thead><tbody id="traces"></tbody></table></div>
<div class="panel wide"><h2>Engine latency</h2><div id="latency"></div></div>
<div class="panel wide"><h2>Architecture drift</h2><pre id="drift" class="muted"></pre></div>
<div class="panel full"><h2>Evidence layers</h2><table><thead><tr><th>Layer</th><th>Status</th><th>Detail</th></tr></thead><tbody id="evidence"></tbody></table></div>
<div class="panel full"><h2>Benchmark history</h2><table><thead><tr><th>Time</th><th>Commit</th><th>Strategies</th></tr></thead><tbody id="bench"></tbody></table></div>
</section>
<script>
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}}[c]));
function bars(target,obj){{const max=Math.max(1,...Object.values(obj||{{}}));document.getElementById(target).innerHTML=Object.entries(obj||{{}}).sort((a,b)=>b[1]-a[1]).map(([k,v])=>`<div>${{esc(k)}} <span class="muted">${{Number(v).toFixed(2)}}</span><div class="bar"><i style="width:${{Math.max(2,100*v/max)}}%"></i></div></div>`).join('')||'<span class="muted">No data yet.</span>'}}
async function load(){{const d=await fetch('/api/overview',{{cache:'no-store'}}).then(r=>r.json());const c=d.runtime.counts||{{}};const cards=[['Files',d.index.tracked],['Graph nodes',d.graph.nodes],['Graph edges',d.graph.edges],['Tokens saved',d.runtime.context_tokens_saved],['Routes',c['route.created']||0],['Engine calls',c['engine.executed']||0],['MCP calls',c['mcp.tool.called']||0],['Reparsed',d.index.files_reparsed]];document.getElementById('metrics').innerHTML=cards.map(([k,v])=>`<div class="card"><div class="muted">${{esc(k)}}</div><div class="metric">${{Number(v||0).toLocaleString()}}</div></div>`).join('');document.getElementById('health').innerHTML=Object.entries(d.health||{{}}).map(([k,v])=>`<span class="pill ${{v?'ok':'bad'}}">${{esc(k)}} · ${{v?'ready':'unavailable'}}</span>`).join('');bars('routes',d.runtime.routes);bars('latency',d.runtime.engine_avg_latency_ms);document.getElementById('hot').innerHTML=(d.graph.hot_nodes||[]).map(x=>`<tr><td>${{esc(x.name)}}</td><td class="muted">${{esc(x.path||'')}}</td><td>${{x.degree}}</td></tr>`).join('');document.getElementById('traces').innerHTML=(d.traces||[]).map(x=>`<tr><td><code>${{esc(x.trace_id.slice(0,10))}}</code></td><td>${{x.spans}}</td><td>${{Number(x.duration_ms).toFixed(1)}}</td><td>${{x.context_tokens}}</td><td>${{x.errors}}</td></tr>`).join('');document.getElementById('drift').textContent=JSON.stringify(d.architecture,null,2);const ev=d.evidence||{{}};document.getElementById('evidence').innerHTML=[['Precision intelligence',ev.precision],['Dependency documentation',ev.dependencies],['Structural engine',ev.structural]].map(([k,v])=>`<tr><td>${{esc(k)}}</td><td class="${{(v&&(v.status==='available'))?'ok':'bad'}}">${{esc((v||{{}}).status||'unknown')}}</td><td class="muted">${{esc((v||{{}}).detail||'')}}</td></tr>`).join('');document.getElementById('bench').innerHTML=(d.benchmarks||[]).slice().reverse().map(x=>`<tr><td>${{esc(x.created_at)}}</td><td><code>${{esc((x.commit||'').slice(0,10))}}</code></td><td>${{esc(Object.keys(x.metrics||{{}}).join(', '))}}</td></tr>`).join('');document.getElementById('updated').textContent='Updated '+new Date().toLocaleTimeString();}}
load().catch(e=>document.getElementById('updated').textContent='Dashboard error: '+e);setInterval(load,15000);
</script></main></body></html>"""


def run_dashboard(runtime: CortexRuntime, host: str = "127.0.0.1", port: int = 7331) -> None:
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, content_type: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'",
            )
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, payload: Any) -> None:
            body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
            self._send(status, "application/json; charset=utf-8", body)

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._send(
                    200,
                    "text/html; charset=utf-8",
                    _html(str(runtime.config.project_root)).encode("utf-8"),
                )
                return
            if parsed.path == "/api/overview":
                self._json(200, asyncio.run(_overview(runtime)))
                return
            if parsed.path == "/api/health":
                self._json(200, asyncio.run(runtime.gateway.health()))
                return
            if parsed.path == "/api/traces":
                self._json(200, {"traces": _recent_traces(runtime, 50)})
                return
            if parsed.path == "/api/benchmarks":
                self._json(200, {"benchmarks": _benchmark_history(runtime, 50)})
                return
            if parsed.path == "/api/pr-risk":
                query = parse_qs(parsed.query)
                base = (query.get("base") or [""])[0]
                head = (query.get("head") or ["HEAD"])[0]
                if not _SAFE_REF.fullmatch(base) or not _SAFE_REF.fullmatch(head):
                    self._json(400, {"error": "invalid git ref"})
                    return
                try:
                    graph = IncrementalGraphIndex(runtime.config.project_root).refresh()[0]
                    report = PRIntelligence(runtime.config.project_root, graph).analyze(base, head)
                except Exception as exc:
                    self._json(422, {"error": f"{type(exc).__name__}: {exc}"})
                    return
                self._json(200, asdict(report))
                return
            self._json(404, {"error": "not found"})

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    server = ThreadingHTTPServer((host, port), Handler)
    try:
        server.serve_forever()
    finally:
        server.server_close()

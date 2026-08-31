"""Small local dashboard for CodeCortex runtime data."""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from codecortex.runtime import CortexRuntime


def _stats(runtime: CortexRuntime) -> dict[str, int]:
    path = runtime.config.state_dir / "runtime" / "events.jsonl"
    counts: Counter[str] = Counter()
    if not path.exists():
        return {}
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        counts[str(payload.get("name", "unknown"))] += 1
    return dict(counts)


def _html(project: str) -> str:
    return f"""<!doctype html>
<html lang=\"en\">
<head>
<meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<title>CodeCortex</title>
<style>
body{{font-family:ui-sans-serif,system-ui;background:#0b0d10;color:#f5f7fa;margin:0;padding:40px}}
main{{max-width:980px;margin:auto}}h1{{font-size:42px;margin-bottom:8px}}p{{color:#aeb7c2}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:14px;margin-top:28px}}
.card{{background:#14181d;border:1px solid #242b33;border-radius:14px;padding:20px}}
.value{{font-size:30px;font-weight:700;margin-top:8px}}code{{color:#d3d9e0}}
</style>
</head>
<body><main><h1>CodeCortex</h1><p><code>{project}</code></p>
<div id=\"grid\" class=\"grid\"></div>
<script>
async function load(){{
 const [health,stats]=await Promise.all([fetch('/api/health').then(r=>r.json()),fetch('/api/stats').then(r=>r.json())]);
 const cards=[['Engines',Object.values(health).filter(Boolean).length],['Routes',stats['route.created']||0],['Engine Calls',stats['engine.executed']||0],['Context Fits',stats['context.fitted']||0]];
 document.getElementById('grid').innerHTML=cards.map(([k,v])=>`<div class=\"card\"><div>${{k}}</div><div class=\"value\">${{v}}</div></div>`).join('');
}}
load();
</script></main></body></html>"""


def run_dashboard(runtime: CortexRuntime, host: str = "127.0.0.1", port: int = 7331) -> None:
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, content_type: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/":
                body = _html(str(runtime.config.project_root)).encode()
                self._send(200, "text/html; charset=utf-8", body)
                return
            if self.path == "/api/health":
                body = json.dumps(asyncio.run(runtime.gateway.health())).encode()
                self._send(200, "application/json", body)
                return
            if self.path == "/api/stats":
                body = json.dumps(_stats(runtime)).encode()
                self._send(200, "application/json", body)
                return
            self._send(404, "application/json", b'{"error":"not found"}')

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    server = ThreadingHTTPServer((host, port), Handler)
    try:
        server.serve_forever()
    finally:
        server.server_close()

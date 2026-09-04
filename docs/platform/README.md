# CodeCortex Platform

CodeCortex Platform is the hosted control plane around the existing CodeCortex intelligence core. It keeps CLI and MCP compatibility while exposing the same product capabilities through `/api/v1` and the React Console.

## Local start

```bash
pip install -e '.[web,parsers]'
cortex-api --host 127.0.0.1 --port 7340
cd web && npm install && npm run dev
```

For the production container path:

```bash
docker compose up --build
```

The Console is exposed on port `7331` and proxies `/api/` to the API service.

## Product hierarchy

`Organization → Workspace → Repository → Revision`

Core intelligence remains repository-local. Organization policy, jobs, audit, notifications and cluster state live in the platform state directory.

## Main surfaces

- Overview and repository explorer
- Knowledge graph and semantic search
- Context Lab and impact analysis
- Routing and traces
- Architecture and drift
- Git and PR intelligence
- Quality and regression gates
- Team memory
- Backends and integrations
- Cluster, workers and jobs
- Organizations, policies and audit
- Approval-gated semantic code actions

# Distributed Scale

CodeCortex 0.5 adds a dependency-light distributed layer while preserving the local-first architecture. The local CLI and stdio MCP server remain the default. Distributed components are opt-in and can be deployed independently.

## Remote shared memory

`SharedMemoryReplica` stores versioned mutations in SQLite and uses version vectors to distinguish causal updates from concurrent writes. Replicas exchange mutations with `cortex_sync_pull` and `cortex_sync_push`. Concurrent updates are resolved deterministically by update timestamp and node identifier while the merged version vector preserves causality. Deletes are replicated as tombstones.

## Persistent vector stores

`PersistentVectorStore` is the stable vector-database contract. `SQLiteVectorStore` is the zero-service persistent provider and supports namespace isolation, durable upserts, deletes, counts, and exact cosine search. Large deployments can register external providers by URI scheme with `register_vector_store_provider`, allowing pgvector, Qdrant, Milvus, Weaviate, or another service to be integrated without coupling the CodeCortex core to a vendor.

## Hosted remote MCP

The `cortex-remote` executable exposes the standard CodeCortex MCP tool surface plus distributed synchronization and worker tools over HTTP or HTTPS.

```bash
export CODECORTEX_REMOTE_TOKEN='replace-with-a-long-random-secret'
cortex-remote --path /srv/repository --host 127.0.0.1 --port 8765 --node-id coordinator-1
```

For a network-facing deployment, terminate with a real certificate or pass a certificate/key pair directly:

```bash
cortex-remote \
  --path /srv/repository \
  --host 0.0.0.0 \
  --port 8765 \
  --node-id coordinator-1 \
  --tls-cert /etc/codecortex/tls/fullchain.pem \
  --tls-key /etc/codecortex/tls/privkey.pem \
  --requests-per-minute 120
```

Authentication uses bearer tokens compared in constant time after hashing. `RemoteAccessPolicy` supports per-principal tool allow lists and global denials. A sliding-window quota is enforced per principal. TLS 1.2 or newer is required when CodeCortex terminates TLS itself. Keep remote endpoints behind a private network, firewall, zero-trust gateway, or equivalent access boundary where possible.

Python clients can use `RemoteMCPClient`:

```python
from codecortex.distributed import RemoteMCPClient

client = RemoteMCPClient("https://cortex.example.com:8765", token="...")
result = client.call("cortex_semantic_search", {"query": "token refresh"})
```

## Multi-node workers

`WorkerCoordinator` provides a durable task queue with capability-aware assignment and worker leases. Nodes register capabilities such as `index`, `retrieve`, or `vector`; incompatible workers never receive a task. Leases can be renewed, completed, failed, or automatically requeued after expiration.

The remote MCP surface exposes worker registration, claiming, and completion, so worker nodes can live on different machines from the coordinator. The coordinator database can be placed on durable storage; service deployments may front it with the authenticated remote transport rather than sharing a filesystem.

## Longitudinal performance history

`PerformanceHistoryStore` stores benchmark snapshots and computes trends for numeric metrics. The `Longitudinal Performance` GitHub Actions workflow runs every Monday and can also be triggered manually. It restores the accumulated database from Actions cache, runs the reproducible production baseline, appends the current commit, exports JSON, and publishes both the current benchmark result and accumulated history as public workflow artifacts.

The workflow is intentionally read-only with respect to repository contents. It does not bypass protected-branch review rules to write benchmark results directly to `main`.

## Organization policy and audit

`OrganizationPolicyStore` adds organization membership, role-based administration, workspaces, tool allow lists, context ceilings, and remote-access policy. Roles are `owner`, `admin`, `member`, and `viewer`. Workspace policies can restrict tool access and remote execution independently.

`AuditLog` records authorization, membership, workspace, and policy events and enforces configurable retention. Audit records are durable SQLite rows and can be queried by organization, workspace, or actor.

## Deployment model

A typical distributed deployment has one or more coordinator instances running `cortex-remote`, a persistent vector service selected through the provider registry, durable organization/audit storage, and any number of indexing/retrieval workers. Shared-memory replicas synchronize through the remote MCP service rather than assuming a shared local filesystem.

The security boundary remains explicit: credentials are never accepted as URL parameters, remote tools are denied unless policy allows them, request bodies are size-limited, quotas are per principal, and TLS can be terminated directly by the service. Production deployments should additionally use secret management, network-level access control, certificate rotation, monitoring, and backup policies appropriate to the environment.

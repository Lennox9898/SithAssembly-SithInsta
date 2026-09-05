# External Components: Current-State Review

Date: 2026-09-04. Reference: `docs/Agentenstack_Evaluationsdossier_2026-09-04.pdf`.

This assessment covers only the current local workspace. It does not adopt software,
start services, or replace project-specific logic. Verify every candidate's current
release, license, security advisories, and compatibility against primary sources
immediately before a proof of concept.

## Existing Architecture Map

| Area | Existing anchor | Assessment |
| --- | --- | --- |
| HTTP and UI | `app.py`, `src/server.py`, `web/` | Local server with API and casework UI. No external gateway is required. |
| Commands | `src/command_engine.py`, `SithAssembly.Runtime.py` | Allowlisted local commands against the case store, not a general shell or tool proxy. |
| Registry and modules | `config/module_registry.json`, `src/module_runtime.py`, `src/assembly_manifest.py` | Explicit `src.*` declarations, controlled loading, and a readable manifest. |
| Coordination | `config/agent_registry.json`, `src/agent_coordination.py`, `src/agent_controller.py` | Local topic and capability model; no external message broker. |
| Data and graph | `src/database.py`, `src/repository.py`, `src/relationship_engine.py`, `src/graph_viewer.py` | SQLite, evidence-bound edges, local groups, and centrality. |
| Analysis | `src/comment_anomaly.py`, `src/ocr_engine.py`, `src/local_llm.py` | Optional local adapters; no silent model downloads or external calls. |
| Evidence and exports | `src/evidence_integrity.py`, `src/evidence_vault.py`, `src/report_generator.py` | Fingerprints, opt-in encrypted packages, and JSON/PDF exports. |
| Telemetry | `src/runtime_logging.py`, `src/runtime_doctor.py` | Local redacted JSONL logs and read-only runtime diagnostics. |
| Deployment | `config/deployment.local.json`, `src/deployment_preflight.py`, `deploy/` | Inactive preparation topology; no cluster is running. |

## Candidates and Integration Boundaries

| Candidate | Status | Justified integration boundary |
| --- | --- | --- |
| IBM ContextForge | Defer | `src/module_runtime.py` and `config/module_registry.json` already solve local registry needs. Benchmark only when multiple external MCP/A2A services exist. |
| agentgateway | Defer | There is no external MCP/A2A or gRPC traffic. A second gateway beside `src/server.py` would duplicate structure. |
| NATS JetStream | Plan a PoC | Fits future `config/agent_registry.json` topics. One event must prove idempotency, replay, backpressure, and failure handling. |
| Temporal | Plan a PoC | Relevant only for an existing long-running, resumable job. The current request model does not need a workflow server. |
| Open Policy Agent | Priority: small PoC | `config/agent_registry.json` contains roles, approvals, and capabilities. A central policy input is valuable only when it fails closed. |
| OpenLineage and Rekor | Reuse concepts | `src/runtime_logging.py`, `src/evidence_integrity.py`, and `src/evidence_vault.py` are the basis. Specify an internal run/artifact envelope first. |
| OpenCTI | Reuse data-model patterns | Deduplication, confidence, source priority, and explicitly `inferred` edges are useful. Do not adopt the full OpenCTI stack. |
| QUT Coordination Network Toolkit | Evaluate methodology | Test platform-neutral coordination features against `src/pattern_engine.py`. Results remain review-required pattern candidates. |
| OSINTGraph | Reference, not core | Compare import, graph, and UI ideas in isolation. Do not couple to fragile access methods. |
| OpenTelemetry and AgentOps | Plan OTel-first | `src/runtime_logging.py` is a local basis. Define a trace contract before an exportable adapter. |
| Firecracker, gVisor, Microsandbox | Evaluate later on server | No gain on the local Windows workstation. Evaluate untrusted workloads only with risk classes and network boundaries. |

## Decision

The next useful change is not a framework import. Prioritize three small, measurable
contracts: a policy input, event envelope, and provenance envelope. They keep the
local architecture compatible with OPA, NATS/JetStream, and OTel without requiring
any of those services. The command core and evidence-bound casework remain central.

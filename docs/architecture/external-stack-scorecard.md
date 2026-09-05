# External Components: Scorecard

Date: 2026-09-04. Scores measure fit with the current codebase, not the quality or
security of a third-party project. Scale: `0` unsuitable, `1` weak, `2` limited,
`3` usable, `4` strong, `5` very strong.

Weights: architecture fit 20%, eliminated project complexity 15%, operational effort
10%, scaling/backpressure 10%, observability/debugging 10%, replaceability 10%,
data/policy control 10%, maturity/maintenance 5%, license/self-hosting 5%, and
migration/rollback 5%. Leave unverifiable criteria open instead of guessing.

| Candidate | Preliminary score | Category | Repository evidence | Condition before a PoC |
| --- | ---: | --- | --- | --- |
| OPA | 3.8 | Plan a PoC | `config/agent_registry.json` has approvals and capabilities but no central policy contract. | Verify the current license, release, and fail-closed Python integration. |
| OpenLineage/Rekor concepts | 3.6 | Reuse concepts | `src/evidence_integrity.py`, `src/evidence_vault.py`, and `src/runtime_logging.py` contain hash and log anchors. | Define a private provenance format; do not export sensitive evidence. |
| NATS JetStream | 3.4 | Plan a PoC | `config/agent_registry.json` already models publishes/subscribes. | An event envelope plus idempotency and replay test must pass. |
| OpenTelemetry | 3.3 | Plan a PoC | `src/runtime_logging.py` redacts locally and `src/runtime_doctor.py` provides diagnostics. | Define trace and redaction contracts first. |
| OpenCTI patterns | 3.2 | Reuse concepts | `src/repository.py`, `src/relationship_engine.py`, and review commands cover relationships, confidence, and hypotheses. | Test the local schema against a deduplication and conflict corpus. |
| Temporal | 2.8 | Plan a PoC | `src/agent_controller.py` represents short stages; no long resumable workflow exists. | Define a real local long-running job with crash/resume behavior. |
| QUT methodology | 2.8 | Reuse concepts | `src/pattern_engine.py` and `src/comment_anomaly.py` are the analysis boundaries. | Use a synthetic corpus, false-positive metrics, and explainability. |
| ContextForge | 2.4 | Defer | `src/module_runtime.py` and `config/module_registry.json` provide local discovery. | Benchmark one gateway use case only after multiple external services exist. |
| agentgateway | 2.2 | Defer | `src/server.py` and the command core cover current local access. | Re-evaluate when actual MCP/A2A or gRPC demand exists. |
| OSINTGraph | 2.0 | Reference | Graph and casework are already in `src/graph_viewer.py` and `src/repository.py`. | Compare only data-model, import, and query ideas. |
| Firecracker/gVisor/Microsandbox | 1.9 | Evaluate later on server | `deploy/` is preflight only and starts no untrusted workers. | Demonstrate the threat model, RuntimeClass, GPU/filesystem needs, and network boundaries. |

## Stop Rules

- No candidate replaces the command core, evidence-bound relationship generation, or human review without a demonstrated benefit.
- Every PoC needs an adapter, measurable exit criteria, and a clean removal path.
- Finalize scores only after release, license, security, and compatibility checks.
- Exclude a service that does not reduce project complexity, provide a better standard, or improve debugging.

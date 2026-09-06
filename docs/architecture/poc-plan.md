# External Components: Bounded PoC Plan

Date: 2026-09-04. This plan is deliberately analysis-first. No section starts a
service, installs dependencies, or migrates data. Every PoC runs alongside the
existing local workflow and must remain removable.

## Phase 0: Contracts Before Infrastructure

1. **Policy input:** A JSON-compatible object for role, module, capability, data
   class, action, and limits. Anchor: `config/agent_registry.json`.
   Success: five existing decisions can be evaluated reproducibly; policy errors deny access.
2. **Event envelope:** `schema_version`, `event_id`, `trace_id`, `occurred_at`,
   `actor`, `subject`, `payload_ref`, and `idempotency_key`. Anchors:
   `src/SithAssembly/Conclave/agent_coordination.py` and
   `src/SithAssembly/AssemblyCore/agent_controller.py`.
   Success: a local simulation detects a duplicate event and deterministically replays a stored sequence.
3. **Provenance envelope:** Run ID, module/model profile, input fingerprint,
   source references, output fingerprint, and error state. Anchors:
   `src/SithAssembly/CipherLedger/evidence_integrity.py`,
   `src/SithAssembly/EvidenceVault/evidence_vault.py`, and `src/runtime_logging.py`.
   Success: an artifact can be traced locally to its integrity and origin without putting plaintext evidence in telemetry.

## Phase 1: Individual, Replaceable PoCs

| PoC | Candidate | Scope | Exit criterion | Stop criterion |
| --- | --- | --- | --- | --- |
| Policy | OPA | Test five fixed local access decisions through an adapter. | Allowed and denied cases are reproducible; failure is fail-closed. | No clear benefit over declarative local rules. |
| Event | NATS JetStream | Test one event type with two producers, three consumers, worker crash, and replay. | No duplicate case action; backpressure and recovery are measurable. | Extra operations without a robustness gain. |
| Workflow | Temporal | Model one long local analysis/import run with checkpoint, timeout, and manual pause. | Crash/resume preserves state and evidence references. | No representative long-running job or excessive operational burden. |
| Telemetry | OpenTelemetry | Create a Command -> Policy -> Worker -> Artifact trace and test redaction. | No secrets or evidence contents in exports; correlation remains traceable. | Unstable trace contract or worse debugging than JSONL. |
| Graph quality | OpenCTI and QUT patterns | Evaluate a synthetic corpus with aliases, conflicts, coordinated, and normal groups. | Confidence, `inferred`, false positives, and evidence links are traceable. | No gain over simpler rules. |

## Order and Guardrails

1. Write the three contracts first and protect them with unit tests.
2. Run no more than one service PoC at a time.
3. Before every PoC, verify primary sources for releases, licenses, advisories, and self-hosting.
4. Do not automate platform activity, collect data without authorization, or export case contents to external observability services.
5. Make a separate integration decision only after a PoC passes.

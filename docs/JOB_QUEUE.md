# Conclave Job Ledger

`SithAssembly//Conclave` has a persistent local job ledger for coordinating approved module work. It is a SQLite-backed queue and audit trail, not an autonomous worker or an external-service adapter.

## Scope

- A job can be queued only for an active agent subscribed to the requested topic in `config/agent_registry.json`.
- Each agent receives a separate job record. The queue does not grant shell, network, model, or direct database capabilities.
- It stores a canonical input hash, the exact registry configuration hash, attempts, state transitions, and immutable event envelopes.
- It does not execute OCR, Depth Anything, collection, LLM, or external-account activity by itself. A later explicit worker adapter must claim a queued job and report its bounded result through the transition API.

## Lifecycle

Valid states are `queued`, `running`, `completed`, `failed`, `needs_review`, and `cancelled`.

- `queued` can become `running` or `cancelled`.
- `running` can become `completed`, `failed`, `needs_review`, or `cancelled`.
- `failed` and `cancelled` jobs can be `requeue`d if attempts remain.
- Completed and review-required jobs cannot be silently restarted.

The idempotency key is `case_id + topic + agent_id + input_hash + configuration_version`. Submitting the same input again returns the existing job rather than creating a duplicate.

`completed` and `needs_review` transitions retain their bounded result object in the job record and its event envelope. This preserves model messages and derived-artifact references without treating either as a verified finding.

## Local API

```text
GET  /api/job-queue
GET  /api/cases/{case_id}/jobs?state=queued
POST /api/cases/{case_id}/jobs
GET  /api/jobs/{job_id}
GET  /api/jobs/{job_id}/events
POST /api/jobs/{job_id}/transition
POST /api/jobs/{job_id}/execute
```

Queue a locally declared topic:

```json
POST /api/cases/1/jobs
{
  "topic": "evidence.depth_requested",
  "input": {"evidence_id": 42},
  "max_attempts": 3
}
```

Record a transition after a bounded worker action:

```json
POST /api/jobs/7/transition
{
  "action": "complete",
  "result": {"artifact_path": "evidence/case-1/derivatives/example.png"},
  "note": "Local Depth Anything derivative created."
}
```

The event endpoint returns the complete envelope for every transition. Case JSON and PDF exports include all jobs and their event trails.

`POST /api/jobs/{job_id}/execute` is an explicit local operator action. At present it supports only the registered `evidence.ocr_requested` and `evidence.depth_requested` routes. Their input must carry the same confirmation flags required by the direct model APIs: `confirm_model_download` for OCR and `confirm_depth_analysis` for depth. Without confirmation, the job is marked `needs_review` and no model is run.

## Storage

- `agent_jobs`: current job state, attempts, input hash, configuration version, and bounded result metadata.
- `agent_job_events`: append-only event envelopes for creation and every lifecycle transition.
- `processing_jobs`: existing human-readable processing timeline; it remains separate from the ledger and receives a compact status entry when jobs are queued or transitioned.

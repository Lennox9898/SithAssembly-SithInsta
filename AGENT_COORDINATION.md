# SithAssembly//Conclave Coordination Contract

This file is the human-readable operating contract for local specialists, modules, and future agent adapters. The machine-readable registry is [`config/agent_registry.json`](config/agent_registry.json). The coordinator may use only registered local roles and topics.

## Editable Policy

This section is intended for human editing. Update it together with the registry when changing operating rules, approvals, role descriptions, or processing order. An agent must not alter this policy on its own.

- Operating objective: local, evidence-bound casework with traceable review candidates.
- Permitted data: manually recorded, explicitly imported, or locally stored evidence.
- Automation: execution mode, frequency, and external adapters are operator decisions. The current local server runs only the implemented local modules; additional execution modes require a separate adapter and explicit configuration.
- Default under uncertainty: return `needs_review` rather than asserting a conclusion.
- Human approvals: `review.decision`, `export.request`, `vault.create`, and `model.download` always require a person.

### Custom Rules

Add case-specific rules here as clear sentences. Example: `Do not run OCR on image evidence before a person has inspected the original.`

## Core Principle

The coordinator routes events. It does not grant unrestricted shell, network, or database access. Every worker returns a verifiable result; only the central persistence layer writes to a case.

## Event Envelope

```json
{
  "event_id": "uuid",
  "topic": "analysis.review_candidate",
  "case_id": 12,
  "input_refs": ["observation:44", "evidence:91"],
  "input_hash": "sha256:...",
  "producer": "signalforge-analysis",
  "configuration_version": "registry:1|model:revision",
  "created_at": "2026-09-04T12:00:00Z",
  "payload": {
    "result_ref": "analysis_run:18"
  }
}
```

`payload` contains only IDs or small, schema-validated metadata. Raw images, vault passphrases, tokens, and large evidence payloads are not transported in agent messages.

## State Handoff Rules

- A worker consumes only topics listed in `subscribes_to` and emits only topics listed in `publishes`.
- A worker returns `completed`, `failed`, or `needs_review`; it never marks a review as accepted.
- The idempotency key is `case_id + topic + input_hash + configuration_version`.
- Repeated requests with the same idempotency key return the existing run rather than creating duplicate edges or OCR output.
- Errors are logged with error class, time, and input references, not raw content or secrets.

## Human Gates

The following topics are the current default human gates and can be changed in the registry:

- `review.decision`
- `export.request`
- `vault.create`
- `model.download`

Additional gates can be added in `config/agent_registry.json`. Required enforcement must exist in server logic; a prompt or agent instruction alone is not access control.

## Account Adapter Configuration

[`config/instagram_accounts.local.json`](config/instagram_accounts.local.json) is the human-editable local inventory for a future account-based adapter. It is intentionally separate from the agent registry because accounts and credentials are operational configuration, not agent capabilities.

- Edit `username`, `purpose`, `execution_profile`, `requested_capabilities`, `agent_topics`, and `operator_notes` directly.
- Keep `enabled` set to `false` until a separate adapter exists and its schedule, scope, and reporting behavior are configured.
- Use `secret_ref` for a local secret-provider reference such as `env:INSTAWATCH_IG_MONITOR_01_PASSWORD`. Do not add a `password` field, session cookie, or token to this file.
- The current server does not read this file, sign in, collect data, or schedule runs. A future adapter should resolve the secret only at runtime and report only connection state and references through `/api/agent-reports`.

### Next Connector Step

The `connector_plan` block is the editable starting point for the future adapter. It reserves the following behavior without enabling it today:

- `startup`: manual, scheduled, or server-start behavior selected by the operator.
- `work_queue`: persistent collection jobs with checkpoints and idempotency keys.
- `quota_mode`: provider-configured pacing, response-aware backoff, and visible usage reporting.
- `failure_strategy`: a paused or failed run is reported to the agent journal and can be resumed from its checkpoint.
- `report_topic`: the topic used by the adapter to report a completed or blocked collection run.

The next code implementation is a queue and adapter boundary, not account-count scaling. Capacity should be measured against the configured provider quota and observed adapter throughput before increasing any workload.

## Clawdbot/OpenClaw Gateway

`SithAssembly//ClawBridge` is a prepared, disabled bridge for `clawdbot.you` and its OpenClaw Gateway. Its local configuration is [`config/clawdbot.local.json`](config/clawdbot.local.json); implementation notes are in [`docs/CLAWDBOT.md`](docs/CLAWDBOT.md).

The server exposes `GET /api/clawdbot` as a secret-free readiness view. The current dispatcher policy is `not_configured`, so ClawBridge does not contact OpenClaw or forward tasks to modules or commands.

`GET /api/clawdbot/manifest` and [`CLAWDBOT_SKILL.md`](CLAWDBOT_SKILL.md) provide the local agent contract: discovery, existing read surfaces, append-only reports, and the implemented CommandDeck endpoint.

Example connection report after a future adapter has run:

```json
{
  "agent_id": "vektorzero-collector",
  "state": "completed",
  "summary": "Configured collection run completed.",
  "output_refs": ["import_batch:24"],
  "connections": [
    {
      "name": "ig_monitor_01",
      "kind": "account_adapter",
      "state": "connected",
      "detail": "Configuration reference: instagram_accounts.local.json"
    }
  ]
}
```

## Agent Reports

An agent can report completed work, output references, and named local connections through the local API. Reports are append-only in `data/agent_reports.jsonl`; they change neither this policy nor the registry.

```text
POST /api/agent-reports
GET /api/agent-reports?limit=100
```

Minimal report:

```json
{
  "agent_id": "signalforge-analysis",
  "case_id": 12,
  "state": "needs_review",
  "summary": "Comment feature scoring finished; two candidates require review.",
  "output_refs": ["analysis_run:18", "observation:44"],
  "connections": [
    {
      "name": "PyOD ECOD",
      "kind": "local_model",
      "state": "used",
      "detail": "Model revision is stored with the analysis run."
    }
  ]
}
```

Allowed states are `completed`, `failed`, `needs_review`, `blocked`, and `info`. Only active agents present in the registry may report. A `connection` is transparent status metadata; it does not open a connection or fetch a URL.

## Connecting a New Agent

1. Add its role, module, allowed topics, and minimum permissions to `config/agent_registry.json`.
2. Implement a narrow request/response schema and a local test adapter.
3. Add unit tests for registry validation, schemas, and idempotency.
4. Start in development mode and inspect `/api/agents`, runtime logs, and output references.
5. Set `enabled: true` only after those checks pass.

An external service or agent framework is not connected by adding a registry entry alone. Every connection requires an explicit, testable adapter with its own configuration and logging.

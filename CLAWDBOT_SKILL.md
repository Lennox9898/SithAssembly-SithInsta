# SithAssembly//ClawBridge Local Skill

Use this document as the local integration contract for a Clawdbot/OpenClaw agent. The SithAssembly server must be running locally before these endpoints are called.

## Discover

```text
GET http://127.0.0.1:8080/api/clawdbot/manifest
GET http://127.0.0.1:8080/api/runtime
GET http://127.0.0.1:8080/api/agents
```

The manifest is the source of truth for this bridge's available capabilities. Read it at startup and after a server restart.

## Available Operations

| Capability | HTTP operation | Purpose |
| --- | --- | --- |
| `runtime.read` | `GET /api/runtime` | Read loaded modules, mode and local log path. |
| `agents.read` | `GET /api/agents` | Read agent roles, topics, routes and Human Gates. |
| `agent_reports.read` | `GET /api/agent-reports?limit=100` | Read append-only work reports. |
| `agent_reports.append` | `POST /api/agent-reports` | Report completed work, references and connections. |
| `commands.execute` | `POST /api/commands` | Run an existing CommandDeck command against the local case database. |
| `cases.read` | `GET /api/cases` and case detail endpoints | Read local casework data. |
| `llm.providers.read` | `GET /api/llm/providers` | Read configured local LLM runtimes and model profiles. |
| `llm.generate` | `POST /api/llm/generate` | Send input to an enabled local LLM and read normalized output. |

`commands.execute` accepts only the CommandDeck command set already implemented by the local server. Use `/help` before relying on a command and preserve returned links and references in the work report.

For local LLMs, read `docs/LOCAL_MODELS.md` first. The model registry is human-editable; only a provider explicitly set to `enabled: true` can receive an LLM request.

## Work Report

After a meaningful operation, append a report:

```json
{
  "agent_id": "vektorzero-collector",
  "case_id": 12,
  "state": "completed",
  "summary": "Normalized the selected local input.",
  "output_refs": ["observation:44"],
  "connections": [
    {
      "name": "SithAssembly local server",
      "kind": "local_http",
      "state": "used",
      "detail": "Runtime manifest checked before work."
    }
  ]
}
```

Use an agent ID that is active in `GET /api/agents`. The journal records references and status, not raw secret values.

## Bridge State

`config/clawdbot.local.json` remains human-editable. `enabled: false` means the project has not started outbound calls to an OpenClaw gateway. The local skill remains useful for a Clawdbot agent that can reach this server through its own local tools or a separately configured bridge.

## Future Handoff

The planned handoff topic is `clawdbot.task_requested`. A future dispatcher must add a persistent queue, idempotency key and result-reference contract before this topic can trigger project work automatically.

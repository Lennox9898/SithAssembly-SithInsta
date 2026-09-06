# Clawdbot/OpenClaw Adapter Preparation

`clawdbot.you` describes a self-hosted assistant built around the OpenClaw Gateway. This project prepares a local bridge configuration only; it does not install OpenClaw, contact a gateway, transmit a token or dispatch any task.

## Local Configuration

- `config/clawdbot.local.json`: human-editable local bridge configuration, ignored by Git.
- `src/clawdbot_adapter.py`: reports configuration state without exposing the token.
- `GET /api/clawdbot`: local status for the bridge preparation.
- `GET /api/clawdbot/manifest`: machine-readable local capability manifest.
- `CLAWDBOT_SKILL.md`: human-readable skill contract for a local Clawdbot agent.

The current official OpenClaw documentation describes the Gateway as the control plane for sessions, channels, tools and events, with loopback binding as the standard default. [Gateway runbook](https://github.com/openclaw/openclaw/blob/main/docs/gateway/index.md), [OpenClaw overview](https://github.com/openclaw/openclaw/blob/main/docs/index.md).

## Configuration Fields

- `gateway.base_url`: local OpenClaw gateway URL. The template uses the documented default port `18789` on loopback.
- `gateway.auth_ref`: environment reference for a gateway token, never a plaintext secret.
- `bridge.agent_id`: the future OpenClaw agent identity used for this project.
- `bridge.allowed_sithassembly_endpoints`: narrow local application surfaces the future skill may read or call.
- `bridge.allowed_openclaw_tools`: intentionally empty until an exact tool allowlist has been reviewed.
- `bridge.idempotency`: requires a stable ID when a future dispatcher hands work between systems.

The configuration loader accepts an HTTP loopback gateway only, requires uppercase `env:` secret references, validates endpoint and tool allowlists, and refuses activation without a non-empty tool allowlist and configured dispatch policy. No outbound dispatcher exists yet.

## Planned Direction

1. Install and configure OpenClaw separately, then verify its local gateway health and active tool inventory.
2. Keep the gateway loopback-only while developing the bridge.
3. Create a dedicated `sithassembly-conclave` OpenClaw agent with only the tools needed for the selected integration.
4. Implement one explicit bridge action at a time, beginning with read-only runtime/agent status.
5. Add a request schema, idempotency key and structured agent report before enabling any task handoff.
6. Set `enabled` to `true` only after a real local gateway test succeeds.

## Local Agent Contract

A Clawdbot agent can use `GET /api/clawdbot/manifest` to discover the existing SithAssembly HTTP contract. The current manifest supports status/case reads, append-only agent reports and the already allowlisted CommandDeck API. See `CLAWDBOT_SKILL.md` for request shapes and reporting expectations.

OpenClaw's `/tools/invoke` HTTP API uses gateway authentication and its tool policy. Its documentation treats the bearer credential as trusted operator access, so the bridge must use a dedicated narrow tool allowlist rather than a broad token-powered dispatcher. [Tools invoke API](https://github.com/openclaw/openclaw/blob/main/docs/gateway/tools-invoke-http-api.md).

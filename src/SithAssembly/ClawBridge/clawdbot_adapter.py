from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


class ClawdbotAdapter:
    """Prepared local OpenClaw/Clawdbot bridge configuration; no gateway calls are made."""

    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path

    def status(self) -> dict[str, Any]:
        config = self._config()
        gateway = config.get("gateway", {})
        bridge = config.get("bridge", {})
        return {
            "provider": config.get("provider", "clawdbot.you / OpenClaw Gateway"),
            "enabled": bool(config.get("enabled", False)),
            "gateway_base_url": gateway.get("base_url"),
            "transport": gateway.get("transport", "local_loopback"),
            "auth_configured": self._secret(gateway.get("auth_ref")) is not None,
            "agent_id": bridge.get("agent_id"),
            "dispatch_policy": bridge.get("dispatch_policy", "not_configured"),
            "allowed_sithassembly_endpoints": bridge.get("allowed_sithassembly_endpoints", []),
            "allowed_openclaw_tools": bridge.get("allowed_openclaw_tools", []),
            "state": "prepared" if not config.get("enabled", False) else "dispatcher_pending",
        }

    def manifest(self) -> dict[str, Any]:
        config = self._config()
        bridge = config.get("bridge", {})
        return {
            "bridge": "SithAssembly//ClawBridge",
            "skill_manifest": config.get("skill_manifest", "CLAWDBOT_SKILL.md"),
            "status": self.status(),
            "capabilities": [
                {"key": "runtime.read", "method": "GET", "path": "/api/runtime"},
                {"key": "agents.read", "method": "GET", "path": "/api/agents"},
                {"key": "agent_reports.read", "method": "GET", "path": "/api/agent-reports?limit=100"},
                {"key": "agent_reports.append", "method": "POST", "path": "/api/agent-reports"},
                {"key": "commands.execute", "method": "POST", "path": "/api/commands"},
                {"key": "cases.read", "method": "GET", "path": "/api/cases"},
            ],
            "planned_handoff": {
                "topic": "clawdbot.task_requested",
                "state": bridge.get("dispatch_policy", "not_configured"),
                "idempotency": bridge.get("idempotency", "required"),
            },
        }

    def _config(self) -> dict[str, Any]:
        try:
            config = json.loads(self.config_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"enabled": False, "provider": "clawdbot.you / OpenClaw Gateway"}
        if not isinstance(config, dict):
            raise ValueError("Clawdbot configuration must be a JSON object")
        return config

    @staticmethod
    def _secret(reference: object) -> str | None:
        if not isinstance(reference, str) or not reference.startswith("env:"):
            return None
        value = os.environ.get(reference.removeprefix("env:"))
        return value if value else None

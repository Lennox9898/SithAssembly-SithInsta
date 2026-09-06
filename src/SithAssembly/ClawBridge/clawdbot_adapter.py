from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


MAX_CLAW_CONFIG_BYTES = 256 * 1024
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
ENV_REFERENCE = re.compile(r"^env:[A-Z][A-Z0-9_]{0,127}$")
TOOL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$")
API_ENDPOINT = re.compile(r"^/api/[A-Za-z0-9_./:-]{1,154}$")


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
            if self.config_path.stat().st_size > MAX_CLAW_CONFIG_BYTES:
                raise ValueError("Clawdbot configuration is limited to 256 KB")
            config = json.loads(self.config_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"enabled": False, "provider": "clawdbot.you / OpenClaw Gateway"}
        if not isinstance(config, dict):
            raise ValueError("Clawdbot configuration must be a JSON object")
        self._validate_config(config)
        return config

    @staticmethod
    def _validate_config(config: dict[str, Any]) -> None:
        if not isinstance(config.get("enabled", False), bool):
            raise ValueError("Clawdbot enabled must be a boolean")
        provider = config.get("provider", "clawdbot.you / OpenClaw Gateway")
        if not isinstance(provider, str) or not provider.strip() or len(provider) > 160:
            raise ValueError("Clawdbot provider must contain 1 to 160 characters")
        gateway = config.get("gateway", {})
        bridge = config.get("bridge", {})
        if not isinstance(gateway, dict) or not isinstance(bridge, dict):
            raise ValueError("Clawdbot gateway and bridge must be JSON objects")

        base_url = gateway.get("base_url")
        if base_url not in (None, ""):
            parsed = urlparse(str(base_url))
            if (
                parsed.scheme != "http"
                or parsed.hostname not in LOOPBACK_HOSTS
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path not in {"", "/"}
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("Clawdbot gateway must use an HTTP loopback base URL")
            try:
                port = parsed.port
            except ValueError as error:
                raise ValueError("Clawdbot gateway has an invalid port") from error
            if port is not None and not 1 <= port <= 65535:
                raise ValueError("Clawdbot gateway has an invalid port")

        if gateway.get("transport", "local_loopback") != "local_loopback":
            raise ValueError("Clawdbot transport must remain local_loopback")
        auth_ref = gateway.get("auth_ref")
        if auth_ref not in (None, "") and (not isinstance(auth_ref, str) or not ENV_REFERENCE.fullmatch(auth_ref)):
            raise ValueError("Clawdbot auth_ref must use an uppercase env: reference")

        endpoints = bridge.get("allowed_sithassembly_endpoints", [])
        tools = bridge.get("allowed_openclaw_tools", [])
        if not ClawdbotAdapter._valid_string_list(endpoints, endpoint=True):
            raise ValueError("Clawdbot endpoint allowlist is invalid")
        if not ClawdbotAdapter._valid_string_list(tools, endpoint=False):
            raise ValueError("Clawdbot tool allowlist is invalid")
        for field in ("agent_id", "dispatch_policy", "idempotency"):
            value = bridge.get(field)
            if value not in (None, "") and (not isinstance(value, str) or TOOL_NAME.fullmatch(value) is None):
                raise ValueError(f"Clawdbot bridge {field} must be a safe string")
        skill_manifest = config.get("skill_manifest", "CLAWDBOT_SKILL.md")
        if (
            not isinstance(skill_manifest, str)
            or len(skill_manifest) > 160
            or Path(skill_manifest).name != skill_manifest
            or not skill_manifest.lower().endswith(".md")
        ):
            raise ValueError("Clawdbot skill_manifest must be a Markdown filename")
        if config.get("enabled") and (not tools or bridge.get("dispatch_policy") == "not_configured"):
            raise ValueError("Clawdbot cannot be enabled without a tool allowlist and configured dispatch policy")

    @staticmethod
    def _valid_string_list(value: object, endpoint: bool) -> bool:
        if not isinstance(value, list) or len(value) > 64:
            return False
        for item in value:
            if not isinstance(item, str) or len(item) > 160:
                return False
            if endpoint:
                if API_ENDPOINT.fullmatch(item) is None or ".." in item:
                    return False
            elif not TOOL_NAME.fullmatch(item):
                return False
        return True

    @staticmethod
    def _secret(reference: object) -> str | None:
        if not isinstance(reference, str) or not ENV_REFERENCE.fullmatch(reference):
            return None
        value = os.environ.get(reference.removeprefix("env:"))
        return value if value else None

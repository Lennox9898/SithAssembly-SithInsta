from __future__ import annotations

import json
import os
import re
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


REQUIRED_AGENT_FIELDS = {"id", "codename", "module", "enabled", "subscribes_to", "publishes", "permissions"}
REPORT_STATES = {"completed", "failed", "needs_review", "blocked", "info"}
MAX_REPORT_REF_CHARS = 1024
MAX_JOURNAL_TAIL_BYTES = 2 * 1024 * 1024
MAX_AGENT_REGISTRY_BYTES = 512 * 1024
MAX_AGENTS = 128
REGISTRY_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,159}$")
PUBLIC_AGENT_FIELDS = ("id", "codename", "module", "enabled", "subscribes_to", "publishes", "permissions")
PUBLIC_AUTOMATION_FIELDS = ("run_mode", "external_adapters", "agent_reports")


class AgentCoordinator:
    """Loads a local capability registry and validates local coordination metadata."""

    def __init__(self, registry_path: Path) -> None:
        self.registry_path = registry_path
        self._registry: dict[str, Any] = {}

    def load(self) -> dict[str, Any]:
        if self.registry_path.stat().st_size > MAX_AGENT_REGISTRY_BYTES:
            raise ValueError("agent registry is limited to 512 KB")
        payload = json.loads(self.registry_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("agent registry must be a JSON object")
        if payload.get("coordination_mode") != "local_deterministic":
            raise ValueError("agent registry must use local_deterministic coordination")
        agents = payload.get("agents")
        if not isinstance(agents, list):
            raise ValueError("agent registry requires an agents array")
        if len(agents) > MAX_AGENTS:
            raise ValueError(f"agent registry is limited to {MAX_AGENTS} agents")
        automation = payload.get("automation", {})
        if not isinstance(automation, dict):
            raise ValueError("agent registry automation must be a JSON object")
        for field in PUBLIC_AUTOMATION_FIELDS:
            if field in automation and not self._valid_registry_token(automation[field]):
                raise ValueError(f"agent registry automation {field} must be a safe string")
        approvals = payload.get("human_approval_required_for", [])
        if (
            not isinstance(approvals, list)
            or len(approvals) > 64
            or not all(self._valid_registry_token(item) for item in approvals)
        ):
            raise ValueError("agent registry human approval rules must contain up to 64 safe strings")

        identifiers: set[str] = set()
        for agent in agents:
            if not isinstance(agent, dict) or not REQUIRED_AGENT_FIELDS.issubset(agent):
                raise ValueError("agent registry contains an incomplete agent entry")
            if (
                not isinstance(agent["id"], str)
                or not REGISTRY_TOKEN.fullmatch(agent["id"])
                or agent["id"] in identifiers
            ):
                raise ValueError("agent ids must be unique non-empty strings")
            if not isinstance(agent["enabled"], bool):
                raise ValueError(f"agent {agent['id']} enabled must be a boolean")
            for field in ("codename", "module"):
                if not self._valid_registry_token(agent[field]):
                    raise ValueError(f"agent {agent['id']} has invalid {field}")
            identifiers.add(agent["id"])
            for field in ("subscribes_to", "publishes", "permissions"):
                if (
                    not isinstance(agent[field], list)
                    or len(agent[field]) > 64
                    or not all(isinstance(item, str) and REGISTRY_TOKEN.fullmatch(item) for item in agent[field])
                ):
                    raise ValueError(f"agent {agent['id']} has invalid {field}")

        self._registry = payload
        return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        agents = self._registry.get("agents", [])
        public_agents = [{field: agent[field] for field in PUBLIC_AGENT_FIELDS} for agent in agents]
        routes: dict[str, list[str]] = {}
        for agent in agents:
            if not agent.get("enabled"):
                continue
            for topic in agent["subscribes_to"]:
                routes.setdefault(topic, []).append(agent["id"])
        return {
            "registry": str(self.registry_path),
            "coordination_mode": self._registry.get("coordination_mode", "not_loaded"),
            "automation": {
                field: self._registry.get("automation", {})[field]
                for field in PUBLIC_AUTOMATION_FIELDS
                if field in self._registry.get("automation", {})
            },
            "human_approval_required_for": list(self._registry.get("human_approval_required_for", [])),
            "active_agents": sum(bool(agent.get("enabled")) for agent in agents),
            "agents": public_agents,
            "routes": routes,
        }

    def active_agent_ids(self) -> set[str]:
        return {agent["id"] for agent in self._registry.get("agents", []) if agent.get("enabled")}

    @staticmethod
    def _valid_registry_token(value: object) -> bool:
        return isinstance(value, str) and REGISTRY_TOKEN.fullmatch(value) is not None

    def validate_report(self, payload: object) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("agent report must be a JSON object")
        agent_id = payload.get("agent_id")
        if not isinstance(agent_id, str) or agent_id not in self.active_agent_ids():
            raise ValueError("agent report requires an active registered agent_id")
        state = payload.get("state")
        if state not in REPORT_STATES:
            raise ValueError(f"agent report state must be one of: {', '.join(sorted(REPORT_STATES))}")
        summary = payload.get("summary")
        if not isinstance(summary, str) or not summary.strip() or len(summary) > 1200:
            raise ValueError("agent report summary must contain 1 to 1200 characters")
        case_id = payload.get("case_id")
        if case_id is not None and (not isinstance(case_id, int) or case_id < 1):
            raise ValueError("agent report case_id must be a positive integer when provided")
        output_refs = self._string_list(payload.get("output_refs", []), "output_refs", 50, MAX_REPORT_REF_CHARS)
        connections = self._connections(payload.get("connections", []))
        return {
            "timestamp": datetime.now(UTC).isoformat(),
            "agent_id": agent_id,
            "case_id": case_id,
            "state": state,
            "summary": summary.strip(),
            "output_refs": output_refs,
            "connections": connections,
        }

    @staticmethod
    def _string_list(value: object, field: str, maximum: int, maximum_chars: int) -> list[str]:
        if (
            not isinstance(value, list)
            or len(value) > maximum
            or not all(isinstance(item, str) and item.strip() and len(item.strip()) <= maximum_chars for item in value)
        ):
            raise ValueError(
                f"agent report {field} must be a list of up to {maximum} non-empty strings "
                f"with at most {maximum_chars} characters each"
            )
        return [item.strip() for item in value]

    @staticmethod
    def _connections(value: object) -> list[dict[str, str]]:
        if not isinstance(value, list) or len(value) > 25:
            raise ValueError("agent report connections must contain at most 25 entries")
        connections = []
        for item in value:
            if not isinstance(item, dict):
                raise ValueError("agent report connection entries must be objects")
            name = item.get("name")
            kind = item.get("kind")
            state = item.get("state")
            detail = item.get("detail", "")
            if not all(isinstance(part, str) and part.strip() for part in (name, kind, state)):
                raise ValueError("agent report connections require name, kind and state")
            if any(len(part.strip()) > 120 for part in (name, kind, state)):
                raise ValueError("agent report connection name, kind and state are limited to 120 characters")
            if not isinstance(detail, str) or len(detail) > 500:
                raise ValueError("agent report connection detail must contain at most 500 characters")
            connections.append({"name": name.strip(), "kind": kind.strip(), "state": state.strip(), "detail": detail.strip()})
        return connections


class AgentReportJournal:
    """Append-only local agent activity journal, separate from human-editable policy."""

    def __init__(self, journal_path: Path) -> None:
        self.journal_path = journal_path
        self._lock = threading.Lock()

    def record(self, coordinator: AgentCoordinator, payload: object) -> dict[str, Any]:
        report = coordinator.validate_report(payload)
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        encoded = (json.dumps(report, ensure_ascii=True, separators=(",", ":")) + "\n").encode("utf-8")
        with self._lock:
            flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
            if hasattr(os, "O_BINARY"):
                flags |= os.O_BINARY
            descriptor = os.open(self.journal_path, flags, 0o600)
            try:
                with os.fdopen(descriptor, "ab") as handle:
                    descriptor = -1
                    handle.write(encoded)
                    handle.flush()
            finally:
                if descriptor >= 0:
                    os.close(descriptor)
            try:
                os.chmod(self.journal_path, 0o600)
            except OSError:
                pass
        return report

    def tail(self, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 500))
        if not self.journal_path.exists():
            return []
        with self.journal_path.open("rb") as handle:
            size = handle.seek(0, os.SEEK_END)
            start = max(0, size - MAX_JOURNAL_TAIL_BYTES)
            handle.seek(start)
            content = handle.read(MAX_JOURNAL_TAIL_BYTES)
        if start:
            separator = content.find(b"\n")
            content = content[separator + 1:] if separator >= 0 else b""
        entries = []
        for raw_line in content.splitlines()[-limit:]:
            try:
                entries.append(json.loads(raw_line.decode("utf-8")))
            except (UnicodeDecodeError, json.JSONDecodeError):
                entries.append({"state": "invalid_log_entry"})
        return entries

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


REQUIRED_AGENT_FIELDS = {"id", "codename", "module", "enabled", "subscribes_to", "publishes", "permissions"}
REPORT_STATES = {"completed", "failed", "needs_review", "blocked", "info"}


class AgentCoordinator:
    """Loads a local capability registry and validates local coordination metadata."""

    def __init__(self, registry_path: Path) -> None:
        self.registry_path = registry_path
        self._registry: dict[str, Any] = {}

    def load(self) -> dict[str, Any]:
        payload = json.loads(self.registry_path.read_text(encoding="utf-8"))
        if payload.get("coordination_mode") != "local_deterministic":
            raise ValueError("agent registry must use local_deterministic coordination")
        agents = payload.get("agents")
        if not isinstance(agents, list):
            raise ValueError("agent registry requires an agents array")

        identifiers: set[str] = set()
        for agent in agents:
            if not isinstance(agent, dict) or not REQUIRED_AGENT_FIELDS.issubset(agent):
                raise ValueError("agent registry contains an incomplete agent entry")
            if not isinstance(agent["id"], str) or not agent["id"] or agent["id"] in identifiers:
                raise ValueError("agent ids must be unique non-empty strings")
            identifiers.add(agent["id"])
            for field in ("subscribes_to", "publishes", "permissions"):
                if not isinstance(agent[field], list) or not all(isinstance(item, str) and item for item in agent[field]):
                    raise ValueError(f"agent {agent['id']} has invalid {field}")

        self._registry = payload
        return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        agents = self._registry.get("agents", [])
        routes: dict[str, list[str]] = {}
        for agent in agents:
            if not agent.get("enabled"):
                continue
            for topic in agent["subscribes_to"]:
                routes.setdefault(topic, []).append(agent["id"])
        return {
            "registry": str(self.registry_path),
            "coordination_mode": self._registry.get("coordination_mode", "not_loaded"),
            "automation": self._registry.get("automation", {}),
            "human_approval_required_for": self._registry.get("human_approval_required_for", []),
            "active_agents": sum(bool(agent.get("enabled")) for agent in agents),
            "agents": agents,
            "routes": routes,
        }

    def active_agent_ids(self) -> set[str]:
        return {agent["id"] for agent in self._registry.get("agents", []) if agent.get("enabled")}

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
        output_refs = self._string_list(payload.get("output_refs", []), "output_refs", 50)
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
    def _string_list(value: object, field: str, maximum: int) -> list[str]:
        if not isinstance(value, list) or len(value) > maximum or not all(isinstance(item, str) and item.strip() for item in value):
            raise ValueError(f"agent report {field} must be a list of up to {maximum} non-empty strings")
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
        with self._lock:
            with self.journal_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(report, ensure_ascii=True, separators=(",", ":")) + "\n")
        return report

    def tail(self, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 500))
        if not self.journal_path.exists():
            return []
        entries = []
        for line in self.journal_path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                entries.append({"state": "invalid_log_entry"})
        return entries

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.agent_coordination import AgentCoordinator
from src.database import open_connection, utc_timestamp


JOB_STATES = frozenset({"queued", "running", "completed", "failed", "needs_review", "cancelled"})
_JSON_LIMIT_BYTES = 1024 * 1024


class PersistentJobQueue:
    """Evidence-local, registry-routed jobs with immutable transition events."""

    def __init__(self, db_path: Path, registry_path: Path) -> None:
        self.db_path = db_path
        self.registry_path = registry_path
        self.coordinator = AgentCoordinator(registry_path)
        self._configuration_version = ""
        self._load_registry()

    def snapshot(self) -> dict[str, Any]:
        registry = self._load_registry()
        return {
            "state": "ready",
            "configuration_version": self._configuration_version,
            "active_agents": registry["active_agents"],
            "routed_topics": sorted(registry["routes"]),
            "states": sorted(JOB_STATES),
        }

    def enqueue(
        self,
        case_id: int,
        topic: str,
        input_payload: dict[str, Any],
        configuration_version: str | None = None,
        max_attempts: int = 3,
    ) -> dict[str, Any]:
        if not isinstance(case_id, int) or case_id < 1:
            raise ValueError("case_id must be a positive integer")
        topic = self._require_text(topic, "topic", 160)
        if not isinstance(input_payload, dict):
            raise ValueError("job input must be a JSON object")
        if not isinstance(max_attempts, int) or not 1 <= max_attempts <= 10:
            raise ValueError("max_attempts must be an integer from 1 to 10")

        registry = self._load_registry()
        agent_ids = registry["routes"].get(topic, [])
        if not agent_ids:
            raise ValueError("topic has no active registered agent route")

        input_json = self._canonical_json(input_payload, "job input")
        input_hash = hashlib.sha256(input_json.encode("utf-8")).hexdigest()
        if configuration_version is not None:
            requested_version = self._require_text(configuration_version, "configuration_version", 160)
            if requested_version != self._configuration_version:
                raise ValueError("configuration_version must match the active agent registry")
        version = self._configuration_version
        queued: list[dict[str, Any]] = []
        with open_connection(self.db_path) as connection:
            self._require_case(connection, case_id)
            for agent_id in agent_ids:
                existing = connection.execute(
                    """SELECT * FROM agent_jobs
                       WHERE case_id = ? AND topic = ? AND agent_id = ?
                         AND input_hash = ? AND configuration_version = ?""",
                    (case_id, topic, agent_id, input_hash, version),
                ).fetchone()
                if existing is not None:
                    queued.append({**self._job_from_row(existing), "created": False})
                    continue

                timestamp = utc_timestamp()
                try:
                    cursor = connection.execute(
                        """INSERT INTO agent_jobs
                           (case_id, topic, agent_id, input_json, input_hash, configuration_version, state,
                            attempt_count, max_attempts, result_json, created_at)
                           VALUES (?, ?, ?, ?, ?, ?, 'queued', 0, ?, '{}', ?)""",
                        (case_id, topic, agent_id, input_json, input_hash, version, max_attempts, timestamp),
                    )
                except sqlite3.IntegrityError:
                    existing = connection.execute(
                        """SELECT * FROM agent_jobs
                           WHERE case_id = ? AND topic = ? AND agent_id = ?
                             AND input_hash = ? AND configuration_version = ?""",
                        (case_id, topic, agent_id, input_hash, version),
                    ).fetchone()
                    if existing is None:
                        raise
                    queued.append({**self._job_from_row(existing), "created": False})
                    continue
                job = self._get_job(connection, int(cursor.lastrowid))
                self._record_event(connection, job, "job.queued", {"source": "explicit_local_request"})
                queued.append({**job, "created": True})

        return {
            "topic": topic,
            "input_hash": input_hash,
            "configuration_version": version,
            "jobs": queued,
        }

    def list_jobs(self, case_id: int, state: str | None = None) -> list[dict[str, Any]]:
        if not isinstance(case_id, int) or case_id < 1:
            raise ValueError("case_id must be a positive integer")
        query = "SELECT * FROM agent_jobs WHERE case_id = ?"
        values: list[Any] = [case_id]
        if state is not None:
            self._require_state(state)
            query += " AND state = ?"
            values.append(state)
        query += " ORDER BY id DESC"
        with open_connection(self.db_path) as connection:
            self._require_case(connection, case_id)
            return [self._job_from_row(row) for row in connection.execute(query, values).fetchall()]

    def get_job(self, job_id: int) -> dict[str, Any] | None:
        if not isinstance(job_id, int) or job_id < 1:
            raise ValueError("job_id must be a positive integer")
        with open_connection(self.db_path) as connection:
            row = connection.execute("SELECT * FROM agent_jobs WHERE id = ?", (job_id,)).fetchone()
            return self._job_from_row(row) if row is not None else None

    def list_events(self, job_id: int) -> list[dict[str, Any]]:
        if not isinstance(job_id, int) or job_id < 1:
            raise ValueError("job_id must be a positive integer")
        with open_connection(self.db_path) as connection:
            if connection.execute("SELECT 1 FROM agent_jobs WHERE id = ?", (job_id,)).fetchone() is None:
                raise ValueError("job not found")
            rows = connection.execute(
                "SELECT event_id, event_type, state, envelope_json, created_at FROM agent_job_events WHERE job_id = ? ORDER BY id ASC",
                (job_id,),
            ).fetchall()
        return [
            {
                "event_id": row["event_id"],
                "event_type": row["event_type"],
                "state": row["state"],
                "envelope": self._json_object(row["envelope_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def transition(self, job_id: int, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if not isinstance(job_id, int) or job_id < 1:
            raise ValueError("job_id must be a positive integer")
        if payload is not None and not isinstance(payload, dict):
            raise ValueError("job transition payload must be a JSON object")
        payload = payload or {}
        action = self._require_text(action, "action", 40).lower()

        with open_connection(self.db_path) as connection:
            job = self._get_job(connection, job_id)
            if action == "start":
                if job["state"] != "queued":
                    raise ValueError("only queued jobs can start")
                if job["attempt_count"] >= job["max_attempts"]:
                    raise ValueError("job reached its maximum attempts")
                timestamp = utc_timestamp()
                connection.execute(
                    """UPDATE agent_jobs SET state = 'running', attempt_count = attempt_count + 1,
                       started_at = ?, error_type = NULL WHERE id = ?""",
                    (timestamp, job_id),
                )
                job = self._get_job(connection, job_id)
                self._record_event(connection, job, "job.started", self._detail(payload))
                return job

            if action == "complete":
                self._require_running(job)
                result = payload.get("result", {})
                if not isinstance(result, dict):
                    raise ValueError("job result must be a JSON object")
                connection.execute(
                    "UPDATE agent_jobs SET state = 'completed', result_json = ?, completed_at = ? WHERE id = ?",
                    (self._canonical_json(result, "job result"), utc_timestamp(), job_id),
                )
                job = self._get_job(connection, job_id)
                self._record_event(connection, job, "job.completed", self._detail(payload, {"result": result}))
                return job

            if action == "fail":
                self._require_running(job)
                error_type = self._require_text(payload.get("error_type"), "error_type", 120)
                connection.execute(
                    "UPDATE agent_jobs SET state = 'failed', error_type = ?, completed_at = ? WHERE id = ?",
                    (error_type, utc_timestamp(), job_id),
                )
                job = self._get_job(connection, job_id)
                self._record_event(connection, job, "job.failed", self._detail(payload, {"error_type": error_type}))
                return job

            if action == "needs_review":
                self._require_running(job)
                result = payload.get("result", {})
                if not isinstance(result, dict):
                    raise ValueError("job result must be a JSON object")
                connection.execute(
                    "UPDATE agent_jobs SET state = 'needs_review', result_json = ?, completed_at = ? WHERE id = ?",
                    (self._canonical_json(result, "job result"), utc_timestamp(), job_id),
                )
                job = self._get_job(connection, job_id)
                self._record_event(connection, job, "job.needs_review", self._detail(payload, {"result": result}))
                return job

            if action == "cancel":
                if job["state"] not in {"queued", "running"}:
                    raise ValueError("only queued or running jobs can be cancelled")
                connection.execute(
                    "UPDATE agent_jobs SET state = 'cancelled', cancelled_at = ? WHERE id = ?",
                    (utc_timestamp(), job_id),
                )
                job = self._get_job(connection, job_id)
                self._record_event(connection, job, "job.cancelled", self._detail(payload))
                return job

            if action == "requeue":
                if job["state"] not in {"failed", "cancelled"}:
                    raise ValueError("only failed or cancelled jobs can be requeued")
                if job["attempt_count"] >= job["max_attempts"]:
                    raise ValueError("job reached its maximum attempts")
                connection.execute(
                    """UPDATE agent_jobs SET state = 'queued', error_type = NULL, started_at = NULL,
                       completed_at = NULL, cancelled_at = NULL, result_json = '{}' WHERE id = ?""",
                    (job_id,),
                )
                job = self._get_job(connection, job_id)
                self._record_event(connection, job, "job.requeued", self._detail(payload))
                return job

        raise ValueError("unsupported job action")

    def _load_registry(self) -> dict[str, Any]:
        registry = self.coordinator.load()
        self._configuration_version = hashlib.sha256(self.registry_path.read_bytes()).hexdigest()
        return registry

    def _record_event(self, connection: sqlite3.Connection, job: dict[str, Any], event_type: str, detail: dict[str, Any]) -> None:
        timestamp = utc_timestamp()
        envelope = {
            "version": 1,
            "event_id": str(uuid4()),
            "event_type": event_type,
            "job_id": job["id"],
            "case_id": job["case_id"],
            "topic": job["topic"],
            "agent_id": job["agent_id"],
            "input_hash": job["input_hash"],
            "configuration_version": job["configuration_version"],
            "state": job["state"],
            "detail": detail,
            "created_at": timestamp,
        }
        connection.execute(
            """INSERT INTO agent_job_events (job_id, event_id, event_type, state, envelope_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (job["id"], envelope["event_id"], event_type, job["state"], self._canonical_json(envelope, "event envelope"), timestamp),
        )

    def _get_job(self, connection: sqlite3.Connection, job_id: int) -> dict[str, Any]:
        row = connection.execute("SELECT * FROM agent_jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise ValueError("job not found")
        return self._job_from_row(row)

    @staticmethod
    def _job_from_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "case_id": row["case_id"],
            "topic": row["topic"],
            "agent_id": row["agent_id"],
            "input": PersistentJobQueue._json_object(row["input_json"]),
            "input_hash": row["input_hash"],
            "configuration_version": row["configuration_version"],
            "state": row["state"],
            "attempt_count": row["attempt_count"],
            "max_attempts": row["max_attempts"],
            "result": PersistentJobQueue._json_object(row["result_json"]),
            "error_type": row["error_type"],
            "created_at": row["created_at"],
            "started_at": row["started_at"],
            "completed_at": row["completed_at"],
            "cancelled_at": row["cancelled_at"],
        }

    @staticmethod
    def _json_object(value: str) -> dict[str, Any]:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _canonical_json(value: dict[str, Any], name: str) -> str:
        try:
            encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError) as error:
            raise ValueError(f"{name} must contain JSON-compatible values") from error
        if len(encoded.encode("utf-8")) > _JSON_LIMIT_BYTES:
            raise ValueError(f"{name} is limited to 1 MB")
        return encoded

    @staticmethod
    def _detail(payload: dict[str, Any], allowed: dict[str, Any] | None = None) -> dict[str, Any]:
        detail = {"note": str(payload.get("note", "")).strip()[:500]}
        if allowed:
            detail.update(allowed)
        return detail

    @staticmethod
    def _require_case(connection: sqlite3.Connection, case_id: int) -> None:
        if connection.execute("SELECT 1 FROM cases WHERE id = ?", (case_id,)).fetchone() is None:
            raise ValueError("case not found")

    @staticmethod
    def _require_running(job: dict[str, Any]) -> None:
        if job["state"] != "running":
            raise ValueError("only running jobs can use this action")

    @staticmethod
    def _require_state(value: str) -> None:
        if value not in JOB_STATES:
            raise ValueError("invalid job state")

    @staticmethod
    def _require_text(value: Any, name: str, maximum: int) -> str:
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
            raise ValueError(f"{name} must contain 1 to {maximum} characters")
        return value.strip()

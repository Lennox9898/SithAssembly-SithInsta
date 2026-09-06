from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from src.job_queue import PersistentJobQueue


@dataclass(frozen=True)
class WorkerOutcome:
    state: str
    result: dict[str, Any] = field(default_factory=dict)
    note: str = ""


JobHandler = Callable[[dict[str, Any]], WorkerOutcome]


class LocalJobWorker:
    """Executes only explicitly supplied local handlers for queued registry jobs."""

    def __init__(self, queue: PersistentJobQueue) -> None:
        self.queue = queue

    def execute(self, job_id: int, handlers: dict[tuple[str, str], JobHandler]) -> dict[str, Any]:
        job = self.queue.get_job(job_id)
        if job is None:
            raise ValueError("job not found")
        if job["state"] != "queued":
            raise ValueError("only queued jobs can be executed")

        running = self.queue.transition(job_id, "start")
        handler = handlers.get((running["topic"], running["agent_id"]))
        if handler is None:
            return self.queue.transition(
                job_id,
                "needs_review",
                {"note": "No local handler is configured for this registered job route."},
            )

        try:
            outcome = handler(running)
            if not isinstance(outcome, WorkerOutcome):
                raise ValueError("local job handler returned an invalid outcome")
            if outcome.state == "completed":
                return self.queue.transition(job_id, "complete", {"result": outcome.result, "note": outcome.note})
            if outcome.state == "needs_review":
                return self.queue.transition(job_id, "needs_review", {"result": outcome.result, "note": outcome.note})
            raise ValueError("local job handler returned an unsupported state")
        except Exception as error:
            return self.queue.transition(
                job_id,
                "fail",
                {"error_type": type(error).__name__, "note": str(error)[:500]},
            )

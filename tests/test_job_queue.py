from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.database import init_db, open_connection, utc_timestamp
from src.job_queue import PersistentJobQueue


class PersistentJobQueueTests(unittest.TestCase):
    def _make_queue(self, root: Path) -> PersistentJobQueue:
        registry_path = root / "agents.json"
        registry_path.write_text(
            json.dumps(
                {
                    "coordination_mode": "local_deterministic",
                    "agents": [
                        {
                            "id": "glyphwatch-depth",
                            "codename": "SithAssembly//GlyphWatch.Depth",
                            "module": "depth_engine",
                            "enabled": True,
                            "subscribes_to": ["evidence.depth_requested"],
                            "publishes": ["evidence.depth_completed"],
                            "permissions": ["derive_explicit_local_image"],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        db_path = root / "queue.db"
        init_db(db_path)
        with open_connection(db_path) as connection:
            connection.execute(
                "INSERT INTO cases (title, description, status, created_at, updated_at) VALUES (?, '', 'open', ?, ?)",
                ("Queue test", utc_timestamp(), utc_timestamp()),
            )
        return PersistentJobQueue(db_path, registry_path)

    def test_enqueue_is_idempotent_and_records_an_event_envelope(self) -> None:
        project_data = Path(__file__).resolve().parent.parent / "data"
        with tempfile.TemporaryDirectory(dir=project_data) as directory:
            queue = self._make_queue(Path(directory))
            first = queue.enqueue(1, "evidence.depth_requested", {"evidence_id": 44})
            second = queue.enqueue(1, "evidence.depth_requested", {"evidence_id": 44})

            self.assertEqual(len(first["jobs"]), 1)
            self.assertTrue(first["jobs"][0]["created"])
            self.assertFalse(second["jobs"][0]["created"])
            self.assertEqual(first["jobs"][0]["id"], second["jobs"][0]["id"])
            events = queue.list_events(first["jobs"][0]["id"])
            self.assertEqual([event["event_type"] for event in events], ["job.queued"])
            self.assertEqual(events[0]["envelope"]["input_hash"], first["input_hash"])

    def test_lifecycle_requeues_failed_work_without_duplicate_jobs(self) -> None:
        project_data = Path(__file__).resolve().parent.parent / "data"
        with tempfile.TemporaryDirectory(dir=project_data) as directory:
            queue = self._make_queue(Path(directory))
            job_id = queue.enqueue(1, "evidence.depth_requested", {"evidence_id": 45})["jobs"][0]["id"]

            with self.assertRaises(ValueError):
                queue.transition(job_id, "complete", {"result": {"state": "completed"}})

            self.assertEqual(queue.transition(job_id, "start")["state"], "running")
            self.assertEqual(queue.transition(job_id, "fail", {"error_type": "ModelUnavailable"})["state"], "failed")
            self.assertEqual(queue.transition(job_id, "requeue")["state"], "queued")
            self.assertEqual(queue.transition(job_id, "start")["attempt_count"], 2)
            completed = queue.transition(job_id, "complete", {"result": {"artifact": "depth.png"}})

            self.assertEqual(completed["state"], "completed")
            self.assertEqual(completed["result"], {"artifact": "depth.png"})
            self.assertEqual(
                [event["event_type"] for event in queue.list_events(job_id)],
                ["job.queued", "job.started", "job.failed", "job.requeued", "job.started", "job.completed"],
            )

    def test_queue_rejects_topics_without_a_registered_route(self) -> None:
        project_data = Path(__file__).resolve().parent.parent / "data"
        with tempfile.TemporaryDirectory(dir=project_data) as directory:
            queue = self._make_queue(Path(directory))
            with self.assertRaisesRegex(ValueError, "active registered agent route"):
                queue.enqueue(1, "model.unregistered_requested", {"model": "unknown"})


if __name__ == "__main__":
    unittest.main()

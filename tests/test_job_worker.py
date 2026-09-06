from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.repository import Repository


class LocalJobWorkerTests(unittest.TestCase):
    def test_depth_job_without_confirmation_stops_for_review(self) -> None:
        project_data = Path(__file__).resolve().parent.parent / "data"
        with tempfile.TemporaryDirectory(dir=project_data) as directory:
            repository = Repository(Path(directory) / "worker.db")
            queued = repository.queue_agent_job(
                1,
                {"topic": "evidence.depth_requested", "input": {"evidence_id": 9}},
            )

            result = repository.execute_agent_job(queued["jobs"][0]["id"])

            self.assertEqual(result["state"], "needs_review")
            self.assertEqual(result["result"]["state"], "confirmation_required")
            self.assertEqual(
                [event["event_type"] for event in repository.get_agent_job_events(result["id"])],
                ["job.queued", "job.started", "job.needs_review"],
            )

    def test_confirmed_depth_job_records_the_bound_model_result(self) -> None:
        project_data = Path(__file__).resolve().parent.parent / "data"
        with tempfile.TemporaryDirectory(dir=project_data) as directory:
            repository = Repository(Path(directory) / "worker.db")
            queued = repository.queue_agent_job(
                1,
                {
                    "topic": "evidence.depth_requested",
                    "input": {"evidence_id": 10, "confirm_depth_analysis": True},
                },
            )
            model_result = {
                "id": 71,
                "evidence_id": 10,
                "state": "completed",
                "engine": "DepthAnythingV2",
                "artifact_path": "evidence/case-1/derivatives/depth.png",
            }

            with patch.object(repository, "run_depth", return_value=model_result) as run_depth:
                result = repository.execute_agent_job(queued["jobs"][0]["id"])

            run_depth.assert_called_once_with(1, 10, confirmed=True)
            self.assertEqual(result["state"], "completed")
            self.assertEqual(result["result"]["artifact_path"], model_result["artifact_path"])

    def test_string_confirmation_does_not_activate_depth_job(self) -> None:
        project_data = Path(__file__).resolve().parent.parent / "data"
        with tempfile.TemporaryDirectory(dir=project_data) as directory:
            repository = Repository(Path(directory) / "worker.db")
            queued = repository.queue_agent_job(
                1,
                {
                    "topic": "evidence.depth_requested",
                    "input": {"evidence_id": 11, "confirm_depth_analysis": "true"},
                },
            )

            result = repository.execute_agent_job(queued["jobs"][0]["id"])

            self.assertEqual(result["state"], "needs_review")
            self.assertEqual(result["result"]["state"], "confirmation_required")


if __name__ == "__main__":
    unittest.main()

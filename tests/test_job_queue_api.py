from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

from src.repository import Repository
from src.server import SignalDeskHandler


class JobQueueApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_repository = SignalDeskHandler.repository
        SignalDeskHandler.repository = Repository(Path(self.temp_dir.name) / "api.db")
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), SignalDeskHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        SignalDeskHandler.repository = self.original_repository
        self.temp_dir.cleanup()

    def test_queue_routes_expose_state_and_event_envelopes(self) -> None:
        queued = self._post(
            "/api/cases/1/jobs",
            {"topic": "evidence.depth_requested", "input": {"evidence_id": 7}},
        )
        self.assertEqual(queued["status"], 201)
        job_id = queued["body"]["jobs"][0]["id"]

        started = self._post(f"/api/jobs/{job_id}/transition", {"action": "start"})
        completed = self._post(
            f"/api/jobs/{job_id}/transition",
            {"action": "complete", "result": {"state": "completed", "artifact_path": "evidence/depth.png"}},
        )
        events = self._get(f"/api/jobs/{job_id}/events")

        self.assertEqual(started["body"]["state"], "running")
        self.assertEqual(completed["body"]["state"], "completed")
        self.assertEqual([item["event_type"] for item in events["body"]], ["job.queued", "job.started", "job.completed"])
        self.assertEqual(events["body"][-1]["envelope"]["agent_id"], "glyphwatch-depth")

    def test_execute_route_requires_the_depth_confirmation_flag(self) -> None:
        queued = self._post(
            "/api/cases/1/jobs",
            {"topic": "evidence.depth_requested", "input": {"evidence_id": 8}},
        )
        job_id = queued["body"]["jobs"][0]["id"]

        executed = self._post(f"/api/jobs/{job_id}/execute", {})

        self.assertEqual(executed["body"]["state"], "needs_review")
        self.assertEqual(executed["body"]["result"]["state"], "confirmation_required")

    def _get(self, path: str) -> dict[str, object]:
        with urlopen(f"{self.base_url}{path}", timeout=5) as response:  # noqa: S310 - loopback test server
            return {"status": response.status, "body": json.loads(response.read().decode("utf-8"))}

    def _post(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=5) as response:  # noqa: S310 - loopback test server
            return {"status": response.status, "body": json.loads(response.read().decode("utf-8"))}


if __name__ == "__main__":
    unittest.main()

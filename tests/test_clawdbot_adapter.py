from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.clawdbot_adapter import ClawdbotAdapter


class ClawdbotAdapterTests(unittest.TestCase):
    def test_disabled_adapter_exposes_only_preparation_state(self) -> None:
        project_data = Path(__file__).resolve().parent.parent / "data"
        with tempfile.TemporaryDirectory(dir=project_data) as directory:
            path = Path(directory) / "clawdbot.json"
            path.write_text(json.dumps({"enabled": False, "gateway": {}, "bridge": {}}), encoding="utf-8")
            status = ClawdbotAdapter(path).status()

        self.assertFalse(status["enabled"])
        self.assertEqual(status["state"], "prepared")

    def test_adapter_reports_auth_presence_without_revealing_secret(self) -> None:
        project_data = Path(__file__).resolve().parent.parent / "data"
        with tempfile.TemporaryDirectory(dir=project_data) as directory:
            path = Path(directory) / "clawdbot.json"
            path.write_text(
                json.dumps(
                    {
                        "enabled": False,
                        "gateway": {"auth_ref": "env:TEST_OPENCLAW_TOKEN"},
                        "bridge": {"allowed_openclaw_tools": []},
                    }
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"TEST_OPENCLAW_TOKEN": "secret-value"}):
                status = ClawdbotAdapter(path).status()

        self.assertTrue(status["auth_configured"])
        self.assertNotIn("secret-value", str(status))

    def test_manifest_exposes_local_capabilities_and_planned_handoff(self) -> None:
        project_data = Path(__file__).resolve().parent.parent / "data"
        with tempfile.TemporaryDirectory(dir=project_data) as directory:
            path = Path(directory) / "clawdbot.json"
            path.write_text(json.dumps({"enabled": False, "bridge": {"dispatch_policy": "not_configured"}}), encoding="utf-8")
            manifest = ClawdbotAdapter(path).manifest()

        self.assertIn("commands.execute", {item["key"] for item in manifest["capabilities"]})
        self.assertEqual(manifest["planned_handoff"]["topic"], "clawdbot.task_requested")

    def test_adapter_rejects_remote_gateway_and_unsafe_enablement(self) -> None:
        project_data = Path(__file__).resolve().parent.parent / "data"
        with tempfile.TemporaryDirectory(dir=project_data) as directory:
            path = Path(directory) / "clawdbot.json"
            path.write_text(
                json.dumps({"enabled": False, "gateway": {"base_url": "https://gateway.example"}, "bridge": {}}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "loopback"):
                ClawdbotAdapter(path).status()

            path.write_text(
                json.dumps({"enabled": True, "gateway": {}, "bridge": {"allowed_openclaw_tools": []}}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "tool allowlist"):
                ClawdbotAdapter(path).status()

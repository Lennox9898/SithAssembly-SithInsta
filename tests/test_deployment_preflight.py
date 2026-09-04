from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.deployment_preflight import DeploymentPreflight


class DeploymentPreflightTests(unittest.TestCase):
    def test_preflight_accepts_env_secret_references_without_starting_services(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            (root / "deploy").mkdir()
            (root / "config" / "deployment.local.json").write_text(json.dumps({"services": {"api": {}}, "secret_references": {"db": "env:DB_PASSWORD"}}), encoding="utf-8")
            (root / "deploy" / "compose.yml").write_text("name: test", encoding="utf-8")
            (root / "deploy" / "Containerfile").write_text("FROM scratch", encoding="utf-8")

            report = DeploymentPreflight(root).snapshot()

        self.assertEqual(report["readiness"], "prepared")
        self.assertEqual(report["activation"], "blocked_pending_operator_gates")

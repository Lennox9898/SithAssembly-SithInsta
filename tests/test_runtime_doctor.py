from __future__ import annotations

import unittest
from pathlib import Path

from src.runtime_doctor import RuntimeDoctor


class RuntimeDoctorTests(unittest.TestCase):
    def test_snapshot_reports_read_only_configuration_and_acceleration(self) -> None:
        root = Path(__file__).resolve().parent.parent
        report = RuntimeDoctor(root).snapshot("auto")

        self.assertEqual(report["compute_mode"], "auto")
        self.assertIn("configuration", report)
        self.assertIn("acceleration", report)
        self.assertIn("cuda_available", report["acceleration"])
        self.assertEqual(report["configuration"]["state"], "ok")
        names = {check["name"] for check in report["configuration"]["checks"]}
        self.assertIn("embedded_model_registry.json", names)

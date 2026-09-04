from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.module_runtime import ModuleRuntime
from src.runtime_logging import RuntimeLogger


class ModuleRuntimeTests(unittest.TestCase):
    def test_loads_explicit_src_modules_and_rejects_other_import_paths(self) -> None:
        project_data = Path(__file__).resolve().parent.parent / "data"
        with tempfile.TemporaryDirectory(dir=project_data) as directory:
            root = Path(directory)
            registry = root / "registry.json"
            registry.write_text(
                json.dumps(
                    {
                        "modules": [
                            {"key": "collector", "import_path": "src.collector", "enabled": True},
                            {"key": "unsafe", "import_path": "os", "enabled": True},
                            {"key": "inactive", "import_path": "src.timeline_engine", "enabled": False},
                        ]
                    }
                ),
                encoding="utf-8",
            )

            runtime = ModuleRuntime(registry)
            states = {item["key"]: item["state"] for item in runtime.startup()}

        self.assertEqual(states["collector"], "loaded")
        self.assertEqual(states["unsafe"], "error")
        self.assertEqual(states["inactive"], "disabled")

    def test_runtime_logger_redacts_passphrase_and_tails_events(self) -> None:
        project_data = Path(__file__).resolve().parent.parent / "data"
        with tempfile.TemporaryDirectory(dir=project_data) as directory:
            logger = RuntimeLogger(Path(directory), dev_mode=True)
            logger.event("vault_requested", passphrase="not-written", visible="ok")
            events = logger.tail()
            content = logger.export_bytes().decode("utf-8")
            logger.close()

        self.assertEqual(events[0]["passphrase"], "[redacted]")
        self.assertNotIn("not-written", content)
        self.assertIn("vault_requested", content)

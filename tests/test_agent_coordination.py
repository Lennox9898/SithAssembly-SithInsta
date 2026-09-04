from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.agent_coordination import AgentCoordinator, AgentReportJournal


class AgentCoordinationTests(unittest.TestCase):
    def test_loads_local_registry_and_builds_topic_routes(self) -> None:
        project_data = Path(__file__).resolve().parent.parent / "data"
        with tempfile.TemporaryDirectory(dir=project_data) as directory:
            registry = Path(directory) / "agents.json"
            registry.write_text(
                json.dumps(
                    {
                        "coordination_mode": "local_deterministic",
                        "agents": [
                            {
                                "id": "worker-a",
                                "codename": "SithAssembly//WorkerA",
                                "module": "collector",
                                "enabled": True,
                                "subscribes_to": ["observation.received"],
                                "publishes": ["observation.normalized"],
                                "permissions": ["normalize_local_input"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            snapshot = AgentCoordinator(registry).load()

        self.assertEqual(snapshot["active_agents"], 1)
        self.assertEqual(snapshot["routes"]["observation.received"], ["worker-a"])

    def test_agent_report_journal_requires_registered_agent_and_keeps_connections(self) -> None:
        project_data = Path(__file__).resolve().parent.parent / "data"
        with tempfile.TemporaryDirectory(dir=project_data) as directory:
            root = Path(directory)
            registry = root / "agents.json"
            registry.write_text(
                json.dumps(
                    {
                        "coordination_mode": "local_deterministic",
                        "agents": [
                            {
                                "id": "worker-a",
                                "codename": "SithAssembly//WorkerA",
                                "module": "collector",
                                "enabled": True,
                                "subscribes_to": ["observation.received"],
                                "publishes": ["observation.normalized"],
                                "permissions": ["normalize_local_input"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            coordinator = AgentCoordinator(registry)
            coordinator.load()
            journal = AgentReportJournal(root / "reports.jsonl")
            report = journal.record(
                coordinator,
                {
                    "agent_id": "worker-a",
                    "case_id": 1,
                    "state": "completed",
                    "summary": "Normalized a local observation.",
                    "output_refs": ["observation:4"],
                    "connections": [{"name": "GlyphWatch", "kind": "local_module", "state": "not_called", "detail": "No image evidence."}],
                },
            )

            self.assertEqual(report["connections"][0]["name"], "GlyphWatch")
            self.assertEqual(journal.tail()[0]["agent_id"], "worker-a")
            with self.assertRaises(ValueError):
                journal.record(coordinator, {"agent_id": "unknown", "state": "info", "summary": "Nope"})

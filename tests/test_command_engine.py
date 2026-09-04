import unittest
from pathlib import Path
from uuid import uuid4

from src.command_engine import CommandEngine
from src.repository import Repository


class CommandEngineTests(unittest.TestCase):
    def test_allowlisted_local_commands(self) -> None:
        db_path = Path("data") / f"test_commands_{uuid4().hex}.db"
        try:
            repo = Repository(db_path)
            case = repo.create_case({"title": "Command test"})
            repo.create_observation(
                {
                    "case_id": case["id"],
                    "handle": "@source",
                    "platform": "instagram",
                    "source_url": "https://example.org/post",
                    "body": "Mentions @target #sample https://example.org/shared.",
                }
            )
            repo.create_observation(
                {
                    "case_id": case["id"],
                    "handle": "@second_source",
                    "platform": "instagram",
                    "source_url": "https://example.org/post",
                    "body": "Second capture also mentions @target.",
                }
            )
            engine = CommandEngine(repo)

            help_result = engine.execute("/help graph", None)
            self.assertEqual(help_result["state"], "completed")
            self.assertTrue(any(key.startswith("/graph build") for key in help_result["data"]))

            find_result = engine.execute("/find posts --query Mentions --limit 10", case["id"])
            self.assertEqual(len(find_result["data"]), 2)

            path_result = engine.execute("/graph path @source @target", case["id"])
            self.assertEqual(len(path_result["data"]), 1)
            self.assertEqual(path_result["data"][0]["relation_type"], "mention")

            activity_result = engine.execute("/profile activity @source", case["id"])
            self.assertGreaterEqual(len(activity_result["data"]), 1)

            comparison_result = engine.execute("/profile compare @source @second_source", case["id"])
            self.assertIn("@target", comparison_result["data"]["shared_connections"])

            common_result = engine.execute("/graph common @source @second_source", case["id"])
            self.assertEqual(common_result["data"], ["@target"])

            duplicate_result = engine.execute("/duplicates --type source", case["id"])
            self.assertGreaterEqual(len(duplicate_result["data"]), 1)

            confidence_result = engine.execute(
                f"/confidence set relationship:{path_result['data'][0]['id']} 0.75",
                case["id"],
            )
            self.assertEqual(confidence_result["data"]["confidence"], 0.75)

            source_result = engine.execute("/source add https://example.org/context --label Context", case["id"])
            self.assertEqual(source_result["data"]["label"], "Context")

            export_result = engine.execute("/export case --format json", case["id"])
            self.assertEqual(export_result["links"][0]["url"], f"/api/cases/{case['id']}/export?format=json")

            blocked_result = engine.execute("/watch add @source", case["id"])
            self.assertEqual(blocked_result["state"], "not_available")

            history_result = engine.execute("/history", case["id"])
            self.assertGreaterEqual(len(history_result["data"]), 1)
        finally:
            if db_path.exists():
                db_path.unlink()


if __name__ == "__main__":
    unittest.main()

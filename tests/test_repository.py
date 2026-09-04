import unittest
from pathlib import Path
from uuid import uuid4

from src.repository import Repository


class RepositoryTests(unittest.TestCase):
    def test_create_observation_and_draft(self) -> None:
        db_path = Path("data") / f"test_repository_{uuid4().hex}.db"
        try:
            repo = Repository(db_path)
            created = repo.create_observation(
                {
                    "platform": "instagram",
                    "handle": "@node_a",
                    "body": "The speaker calls people vermin and tells followers to join our group.",
                    "sources": [
                        {
                            "title": "Reference",
                            "url": "https://example.org/reference",
                            "excerpt": "Recruitment into closed groups can pair with dehumanizing language.",
                        }
                    ],
                    "relationships": [
                        {
                            "handle": "@node_b",
                            "relation_type": "co-mentioned",
                            "weight": 0.6,
                        }
                    ],
                }
            )
            self.assertEqual(created["actor"]["handle"], "@node_a")
            self.assertEqual(len(created["relationships"]), 1)

            drafted = repo.create_draft(created["observation"]["id"], tone="firm")
            self.assertIsNotNone(drafted)
            self.assertEqual(drafted["draft"]["tone"], "firm")

            network = repo.get_network()
            self.assertEqual(len(network["actors"]), 2)
            self.assertEqual(len(network["edges"]), 1)
        finally:
            if db_path.exists():
                db_path.unlink()


if __name__ == "__main__":
    unittest.main()

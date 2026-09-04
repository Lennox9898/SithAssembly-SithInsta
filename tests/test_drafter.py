import unittest

from src.drafter import compose_draft


class DrafterTests(unittest.TestCase):
    def test_blocks_draft_without_sources(self) -> None:
        draft = compose_draft({"danger_flags": ["conspiracy"]}, [], tone="firm")
        self.assertEqual(draft["state"], "blocked_missing_sources")

    def test_generates_source_bound_draft(self) -> None:
        draft = compose_draft(
            {"danger_flags": ["dehumanization", "recruitment"]},
            [
                {
                    "title": "Institute Report",
                    "url": "https://example.org/report",
                    "excerpt": "Closed-group recruitment often accompanies dehumanizing narratives.",
                }
            ],
            tone="sharp",
        )
        self.assertEqual(draft["tone"], "sharp")
        self.assertIn("Institute Report", draft["body"])
        self.assertIn("https://example.org/report", draft["body"])


if __name__ == "__main__":
    unittest.main()


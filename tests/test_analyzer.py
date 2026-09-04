import unittest

from src.analyzer import score_text


class AnalyzerTests(unittest.TestCase):
    def test_detects_multiple_signals(self) -> None:
        result = score_text(
            "The post calls people vermin, says history was fabricated, and asks readers to join our group."
        )
        self.assertGreaterEqual(result.risk_level, 60)
        self.assertIn("dehumanization", result.danger_flags)
        self.assertIn("historical_denial", result.danger_flags)
        self.assertIn("recruitment", result.danger_flags)

    def test_returns_low_score_without_matches(self) -> None:
        result = score_text("This post needs more review, but it contains no obvious trigger pattern.")
        self.assertEqual(result.risk_level, 0)
        self.assertEqual(result.severity, "niedrig")


if __name__ == "__main__":
    unittest.main()


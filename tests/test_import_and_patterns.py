import unittest
from pathlib import Path
from uuid import uuid4

from src.repository import Repository


class ImportAndPatternTests(unittest.TestCase):
    def test_import_creates_fingerprints_and_evidence_bound_patterns(self) -> None:
        db_path = Path("data") / f"test_patterns_{uuid4().hex}.db"
        try:
            repo = Repository(db_path)
            case = repo.create_case({"title": "Pattern test"})
            result = repo.import_case_payload(
                case["id"],
                {
                    "label": "Reviewed export",
                    "items": [
                        {
                            "handle": "@first_account",
                            "platform": "instagram",
                            "source_url": "https://example.org/first",
                            "body": "Shared sample text #shared https://shared.example/resource",
                        },
                        {
                            "handle": "@second_account",
                            "platform": "instagram",
                            "source_url": "https://example.org/second",
                            "body": "Shared sample text #shared https://shared.example/resource",
                        },
                        {"handle": "@invalid"},
                    ],
                },
            )
            self.assertEqual(result["accepted_count"], 2)
            self.assertEqual(result["rejected_count"], 1)

            findings = repo.get_case_findings(case["id"])
            kinds = {finding["kind"] for finding in findings}
            self.assertIn("shared_hashtag", kinds)
            self.assertIn("shared_domain", kinds)
            self.assertIn("repeated_content", kinds)

            batches = repo.list_import_batches(case["id"])
            self.assertEqual(batches[0]["accepted_count"], 2)
        finally:
            if db_path.exists():
                db_path.unlink()


if __name__ == "__main__":
    unittest.main()

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

    def test_import_rejects_unsafe_urls_without_aborting_valid_items(self) -> None:
        db_path = Path("data") / f"test_import_urls_{uuid4().hex}.db"
        try:
            repo = Repository(db_path)
            case = repo.create_case({"title": "URL import validation"})
            result = repo.import_case_payload(
                case["id"],
                {"items": [
                    {"handle": "@valid", "body": "Captured text", "source_url": "https://example.org/post"},
                    {"handle": "@unsafe", "body": "Captured text", "source_url": "javascript:alert(1)"},
                ]},
            )
            self.assertEqual(result["accepted_count"], 1)
            self.assertEqual(result["rejected_count"], 1)
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_import_rejects_non_string_fields_and_invalid_ports(self) -> None:
        db_path = Path("data") / f"test_import_types_{uuid4().hex}.db"
        try:
            repo = Repository(db_path)
            case = repo.create_case({"title": "Import type validation"})
            result = repo.import_case_payload(
                case["id"],
                {
                    "items": [
                        {"handle": ["not", "text"], "body": "Captured text"},
                        {"handle": "@invalid_port", "body": "Captured text", "source_url": "https://example.org:bad/post"},
                    ]
                },
            )

            self.assertEqual(result["accepted_count"], 0)
            self.assertEqual(result["rejected_count"], 2)
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_import_reports_late_schema_errors_without_losing_valid_items(self) -> None:
        db_path = Path("data") / f"test_import_partial_{uuid4().hex}.db"
        try:
            repo = Repository(db_path)
            case = repo.create_case({"title": "Import consistency"})
            result = repo.import_case_payload(
                case["id"],
                {
                    "items": [
                        {"handle": "@valid", "body": "Valid imported evidence."},
                        {"handle": "@invalid", "body": "Invalid optional field.", "platform": ["instagram"]},
                    ]
                },
            )

            self.assertEqual(result["accepted_count"], 1)
            self.assertEqual(result["rejected_count"], 1)
            self.assertEqual(len(repo.list_case_observations(case["id"])), 1)
        finally:
            if db_path.exists():
                db_path.unlink()


if __name__ == "__main__":
    unittest.main()

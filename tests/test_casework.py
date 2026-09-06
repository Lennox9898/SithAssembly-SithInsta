import unittest
from pathlib import Path
from uuid import uuid4

from src.report_generator import ReportGenerator
from src.repository import Repository


class CaseworkTests(unittest.TestCase):
    def test_case_evidence_graph_and_exports(self) -> None:
        db_path = Path("data") / f"test_casework_{uuid4().hex}.db"
        try:
            repo = Repository(db_path)
            case = repo.create_case({"title": "Testfall", "description": "Evidence chain"})
            created = repo.create_observation(
                {
                    "case_id": case["id"],
                    "handle": "@source_account",
                    "platform": "instagram",
                    "display_name": "Source Account",
                    "source_url": "https://example.org/post/1",
                    "captured_at": "2026-09-04T12:00:00Z",
                    "profile_bio": "First profile text",
                    "body": "A captured post mentions @linked_account #recurring and https://example.org/shared.",
                }
            )
            observation_id = created["observation"]["id"]
            detail = repo.get_observation(observation_id)
            self.assertIsNotNone(detail)
            self.assertIn("#recurring", [tag["label"] for tag in detail["tags"]])
            self.assertGreaterEqual(len(detail["evidence"]), 2)

            graph = repo.get_case_graph(case["id"])
            self.assertEqual(len(graph["edges"]), 1)
            self.assertEqual(len(graph["nodes"]), 2)
            self.assertEqual(graph["edges"][0]["relation_type"], "mention")

            repo.add_note(case["id"], {"body": "Reviewed with original URL.", "observation_id": observation_id})
            repo.add_identity_claim(
                case["id"],
                {
                    "actor_id": detail["actor"]["id"],
                    "candidate_label": "Analyst-provided alias",
                    "basis": "Self-declared in the captured profile.",
                    "confidence": 0.45,
                    "state": "unverified",
                    "evidence_observation_id": observation_id,
                },
            )
            report = repo.export_case(case["id"])
            self.assertIsNotNone(report)
            self.assertEqual(len(report["identity_hypotheses"]), 1)
            self.assertGreaterEqual(len(report["timeline"]), 3)
            self.assertIn(b"Testfall", ReportGenerator().pdf_bytes(report))
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_case_references_cannot_cross_case_boundaries(self) -> None:
        db_path = Path("data") / f"test_casework_boundaries_{uuid4().hex}.db"
        try:
            repo = Repository(db_path)
            first_case = repo.create_case({"title": "First case"})
            second_case = repo.create_case({"title": "Second case"})
            second = repo.create_observation(
                {
                    "case_id": second_case["id"],
                    "handle": "@second_case_actor",
                    "body": "Evidence belonging only to the second case.",
                }
            )
            observation_id = second["observation"]["id"]
            actor_id = second["actor"]["id"]

            with self.assertRaisesRegex(ValueError, "observation not found in case"):
                repo.add_note(first_case["id"], {"body": "Invalid link", "observation_id": observation_id})
            with self.assertRaisesRegex(ValueError, "actor not found in case"):
                repo.add_identity_claim(
                    first_case["id"],
                    {
                        "actor_id": actor_id,
                        "candidate_label": "Invalid identity link",
                        "basis": "The referenced actor belongs to another case.",
                    },
                )
            with self.assertRaisesRegex(ValueError, "observation not found in case"):
                repo.add_screenshot(
                    first_case["id"],
                    {
                        "label": "Invalid screenshot link",
                        "url": "https://example.org/screenshot",
                        "observation_id": observation_id,
                    },
                )
        finally:
            if db_path.exists():
                db_path.unlink()


if __name__ == "__main__":
    unittest.main()

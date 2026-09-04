import json
import shutil
import unittest
from pathlib import Path
from uuid import uuid4

from src.repository import Repository


TINY_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/"
    "fI7RZQAAAABJRU5ErkJggg=="
)


class EvidenceVaultTests(unittest.TestCase):
    def test_creates_and_verifies_signed_encrypted_case_package(self) -> None:
        workspace = Path("data") / f"test-evidence-vault-{uuid4().hex}"
        try:
            workspace.mkdir(parents=True)
            repository = Repository(workspace / "case.db")
            case = repository.create_case({"title": "Vault test"})
            observation = repository.create_observation(
                {"case_id": case["id"], "handle": "@source", "body": "Captured local evidence"}
            )
            repository.add_local_image(
                case["id"],
                {
                    "label": "Capture",
                    "observation_id": observation["observation"]["id"],
                    "content_base64": TINY_PNG,
                },
            )

            created = repository.create_evidence_vault(
                case["id"],
                "correct horse battery staple",
                "test analyst",
            )
            verified = repository.verify_evidence_vault(created["id"])
            package = repository.read_evidence_vault(created["id"])

            self.assertEqual(verified["state"], "valid")
            self.assertIsNotNone(package)
            self.assertGreaterEqual(created["file_count"], 2)
            container = json.loads(package[1].decode("utf-8"))
            self.assertEqual(container["header"]["magic"], "SITHASSEMBLY-EVIDENCE-VAULT")
            self.assertNotIn("correct horse", package[1].decode("utf-8"))
        finally:
            shutil.rmtree(workspace, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

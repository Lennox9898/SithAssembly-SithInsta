import json
import base64
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

    def test_rejects_image_evidence_with_excessive_dimensions(self) -> None:
        workspace = Path("data") / f"test-image-limit-{uuid4().hex}"
        try:
            workspace.mkdir(parents=True)
            repository = Repository(workspace / "case.db")
            case = repository.create_case({"title": "Image limit test"})
            oversized_png = (
                b"\x89PNG\r\n\x1a\n"
                + b"\x00\x00\x00\rIHDR"
                + (100_000).to_bytes(4, "big")
                + (100_000).to_bytes(4, "big")
                + b"\x08\x02\x00\x00\x00"
            )

            with self.assertRaisesRegex(ValueError, "40 megapixels"):
                repository.add_local_image(
                    case["id"],
                    {"label": "Oversized", "content_base64": base64.b64encode(oversized_png).decode("ascii")},
                )
        finally:
            shutil.rmtree(workspace, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

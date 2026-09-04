import base64
import shutil
import unittest
from pathlib import Path
from uuid import uuid4

from src.comment_anomaly import CommentAnomalyEngine
from src.repository import Repository


TINY_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/"
    "fI7RZQAAAABJRU5ErkJggg=="
)


class ModelAdapterTests(unittest.TestCase):
    def test_comment_engine_returns_review_only_candidates(self) -> None:
        observations = [
            {
                "id": index,
                "content_type": "reel_comment",
                "actor_handle": f"@account_{index}",
                "source_url": f"https://example.test/{index}",
                "body": "normal comment",
            }
            for index in range(1, 5)
        ]
        observations.append(
            {
                "id": 5,
                "content_type": "reel_comment",
                "actor_handle": "@outlier",
                "source_url": "https://example.test/5",
                "body": "LOUD!!! " * 50 + "https://example.test @target #tag",
            }
        )

        result = CommentAnomalyEngine().analyze(observations)

        self.assertEqual(result["state"], "completed")
        self.assertIn(result["method"], {"robust_baseline", "pyod_ecod"})
        self.assertTrue(all(item["state"] == "review_required" for item in result["candidates"]))

    def test_local_image_is_stored_and_ocr_requires_confirmation(self) -> None:
        workspace = Path("data") / f"test-model-adapter-{uuid4().hex}"
        try:
            workspace.mkdir(parents=True)
            repo = Repository(workspace / "case.db")
            case = repo.create_case({"title": "Image test"})
            observation = repo.create_observation(
                {
                    "case_id": case["id"],
                    "handle": "@source",
                    "body": "Captured comment",
                    "content_type": "reel_comment",
                }
            )
            evidence = repo.add_local_image(
                case["id"],
                {
                    "label": "Local capture",
                    "observation_id": observation["observation"]["id"],
                    "content_base64": TINY_PNG,
                },
            )

            self.assertTrue((workspace / evidence["file_path"]).exists())
            pending = repo.run_ocr(case["id"], evidence["id"])
            self.assertEqual(pending["state"], "confirmation_required")
        finally:
            shutil.rmtree(workspace, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

import base64
import shutil
import unittest
from pathlib import Path
from uuid import uuid4

from src.comment_anomaly import CommentAnomalyEngine
from src.depth_engine import LocalDepthEngine
from src.ocr_engine import LocalOcrEngine
from src.repository import Repository


TINY_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/"
    "fI7RZQAAAABJRU5ErkJggg=="
)


class ModelAdapterTests(unittest.TestCase):
    def test_ocr_profile_is_configured_for_local_hugging_face_cache(self) -> None:
        status = LocalOcrEngine().status()

        self.assertEqual(status["profile"], "GlyphWatch.PP-OCRv6-Small/1.1")
        self.assertEqual(status["runtime"], "PaddleOCR with Transformers")
        self.assertTrue(status["cache_dir"].endswith(".runtime\\huggingface"))
        self.assertTrue(status["paddlex_cache_dir"].endswith(".runtime\\paddlex"))
        self.assertEqual(status["model_download"], "preloaded")

    def test_depth_profile_is_pinned_to_the_local_model_directory(self) -> None:
        status = LocalDepthEngine().status()

        self.assertEqual(status["profile"], "GlyphWatch.DepthAnythingV2-Small/1.0")
        self.assertEqual(status["runtime"], "Transformers with PyTorch")
        self.assertTrue(status["model_dir"].endswith(".runtime\\models\\Depth-Anything-V2-Small-hf"))
        self.assertEqual(status["model_download"], "preloaded")
        self.assertTrue(status["model"]["local_only"])

    def test_depth_derivation_requires_confirmation(self) -> None:
        workspace = Path("data") / f"test-depth-adapter-{uuid4().hex}"
        try:
            workspace.mkdir(parents=True)
            repo = Repository(workspace / "case.db")
            case = repo.create_case({"title": "Depth test"})
            evidence = repo.add_local_image(
                case["id"],
                {"label": "Local capture", "content_base64": TINY_PNG},
            )

            pending = repo.run_depth(case["id"], evidence["id"])

            self.assertEqual(pending["state"], "confirmation_required")
        finally:
            shutil.rmtree(workspace, ignore_errors=True)

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

from __future__ import annotations

import hashlib
from importlib.util import find_spec
import json
import math
import os
from pathlib import Path
from typing import Any


class LocalDepthEngine:
    """Optional local Depth Anything adapter for explicit image evidence only."""

    PROFILE_ID = "GlyphWatch.DepthAnythingV2-Small/1.0"

    def __init__(self, registry_path: Path | None = None) -> None:
        root_dir = Path(__file__).resolve().parents[3]
        self.registry_path = registry_path or root_dir / "config" / "embedded_model_registry.json"
        self.root_dir = root_dir

    def _profile(self) -> dict[str, Any]:
        payload = json.loads(self.registry_path.read_text(encoding="utf-8"))
        for profile in payload.get("profiles", []):
            if profile.get("id") == self.PROFILE_ID:
                return profile
        raise ValueError(f"Depth profile {self.PROFILE_ID} is missing from {self.registry_path}")

    def _model_dir(self, profile: dict[str, Any]) -> Path:
        override = os.environ.get("SITH_DEPTH_ANYTHING_MODEL_DIR")
        if override:
            return Path(override).resolve()
        configured = Path(str(profile["model_dir"]))
        return configured if configured.is_absolute() else (self.root_dir / configured).resolve()

    @staticmethod
    def _dependencies_available() -> bool:
        return all(find_spec(package) is not None for package in ("transformers", "torch", "PIL"))

    @staticmethod
    def _device(profile: dict[str, Any]) -> str:
        configured = str(profile.get("device", "auto"))
        if configured != "auto":
            return configured
        try:
            import torch

            return "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            return "cpu"

    @staticmethod
    def _model_is_available(model_dir: Path) -> bool:
        return all((model_dir / filename).is_file() for filename in ("config.json", "model.safetensors", "preprocessor_config.json"))

    def status(self) -> dict[str, Any]:
        profile = self._profile()
        model_dir = self._model_dir(profile)
        model_available = self._model_is_available(model_dir)
        available = bool(profile.get("enabled")) and model_available and self._dependencies_available()
        return {
            "key": "relative_depth",
            "module": "SithAssembly//GlyphWatch",
            "profile": self.PROFILE_ID,
            "state": "available" if available else "not_installed",
            "dependency": "transformers + PyTorch + Pillow",
            "runtime": str(profile["runtime"]),
            "device": self._device(profile),
            "model_dir": str(model_dir),
            "model_download": "preloaded" if model_available else "missing",
            "model": {
                "repository": str(profile["repository"]),
                "revision": str(profile["revision"]),
                "local_only": True,
            },
            "output": dict(profile["output"]),
            "input": "local JPEG, PNG, GIF or WebP evidence",
        }

    def derive(self, image_path: Path, output_path: Path) -> dict[str, Any]:
        status = self.status()
        if status["state"] != "available":
            return {
                "state": "not_installed",
                "engine": "Depth Anything V2",
                "profile": self.PROFILE_ID,
                "message": "Transformers, PyTorch, Pillow, or the local model snapshot is unavailable. No depth derivative was created.",
            }

        import torch
        import torch.nn.functional as functional
        from PIL import Image
        from transformers import AutoImageProcessor, AutoModelForDepthEstimation

        profile = self._profile()
        model_dir = self._model_dir(profile)
        device = self._device(profile)
        with Image.open(image_path) as source:
            image = source.convert("RGB")
        width, height = image.size
        processor = AutoImageProcessor.from_pretrained(model_dir, local_files_only=True)
        model = AutoModelForDepthEstimation.from_pretrained(model_dir, local_files_only=True)
        model.to(device)
        model.eval()
        inputs = processor(images=image, return_tensors="pt")
        inputs = {key: value.to(device) for key, value in inputs.items()}
        with torch.inference_mode():
            prediction = model(**inputs).predicted_depth
            prediction = functional.interpolate(
                prediction.unsqueeze(1),
                size=(height, width),
                mode="bicubic",
                align_corners=False,
            ).squeeze()

        prediction = torch.nan_to_num(prediction.float(), nan=0.0, posinf=0.0, neginf=0.0).cpu()
        minimum = float(prediction.min().item())
        maximum = float(prediction.max().item())
        span = maximum - minimum
        normalized = torch.zeros_like(prediction) if math.isclose(span, 0.0) else (prediction - minimum) / span
        depth_16 = (normalized.clamp(0, 1) * 65535).round().to(torch.uint16).numpy()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(depth_16, mode="I;16").save(output_path, format="PNG")
        artifact_sha256 = hashlib.sha256(output_path.read_bytes()).hexdigest()

        return {
            "state": "completed",
            "engine": "Depth Anything V2",
            "profile": self.PROFILE_ID,
            "model": status["model"],
            "device": device,
            "relative_depth": True,
            "source_size": {"width": width, "height": height},
            "raw_range": {"minimum": round(minimum, 6), "maximum": round(maximum, 6)},
            "artifact_path": str(output_path),
            "artifact_sha256": artifact_sha256,
            "message": "Relative-depth derivative completed for explicit local image evidence.",
        }

from __future__ import annotations

import hashlib
from importlib.util import find_spec
import math
import os
from pathlib import Path
import re
from typing import Any

from src.SithAssembly.GlyphWatch.embedded_registry import EmbeddedModelRegistry


class LocalDepthEngine:
    """Optional local Depth Anything adapter for explicit image evidence only."""

    PROFILE_ID = "GlyphWatch.DepthAnythingV2-Small/1.0"

    def __init__(self, registry_path: Path | None = None) -> None:
        root_dir = Path(__file__).resolve().parents[3]
        self.registry_path = registry_path or root_dir / "config" / "embedded_model_registry.json"
        self.root_dir = root_dir

    def _profile(self) -> dict[str, Any]:
        profile = EmbeddedModelRegistry(self.registry_path).profile(self.PROFILE_ID)
        if not isinstance(profile.get("enabled"), bool):
            raise ValueError("depth profile enabled must be a boolean")
        runtime = profile.get("runtime")
        if not isinstance(runtime, str) or not runtime.strip() or len(runtime) > 120:
            raise ValueError("depth profile runtime must contain 1 to 120 characters")
        repository = profile.get("repository")
        if not isinstance(repository, str) or re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}/[A-Za-z0-9][A-Za-z0-9._-]{0,127}",
            repository,
        ) is None:
            raise ValueError("depth profile repository is invalid")
        revision = profile.get("revision")
        if not isinstance(revision, str) or re.fullmatch(r"[0-9a-f]{40}", revision) is None:
            raise ValueError("depth profile revision must be a full commit hash")
        model_dir = profile.get("model_dir")
        if not isinstance(model_dir, str) or not model_dir or len(model_dir) > 1024 or "\x00" in model_dir:
            raise ValueError("depth profile model_dir is invalid")
        if not re.fullmatch(r"auto|cpu|cuda(?::[0-9]{1,2})?", str(profile.get("device", "auto"))):
            raise ValueError("depth profile device is invalid")
        output = profile.get("output")
        if (
            not isinstance(output, dict)
            or output.get("format") != "png"
            or output.get("bit_depth") != 16
            or output.get("kind") != "relative_depth_derivative"
        ):
            raise ValueError("depth profile output contract is invalid")
        return profile

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

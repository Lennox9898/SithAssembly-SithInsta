from __future__ import annotations

from importlib.util import find_spec
import json
import os
from pathlib import Path
import re
from typing import Any

from src.SithAssembly.GlyphWatch.embedded_registry import EmbeddedModelRegistry


MAX_OCR_LINES = 10_000
MAX_OCR_LINE_CHARS = 8_192
MAX_OCR_TEXT_CHARS = 1024 * 1024
MAX_OCR_RESULT_DEPTH = 32
MODEL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$")
REPOSITORY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}/[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class LocalOcrEngine:
    """Optional local PP-OCRv6 adapter for explicit image evidence only."""

    PROFILE_ID = "GlyphWatch.PP-OCRv6-Small/1.1"

    def __init__(self, registry_path: Path | None = None) -> None:
        root_dir = Path(__file__).resolve().parents[3]
        self.registry_path = registry_path or root_dir / "config" / "embedded_model_registry.json"
        self.root_dir = root_dir

    def _profile(self) -> dict[str, Any]:
        profile = EmbeddedModelRegistry(self.registry_path).profile(self.PROFILE_ID)
        if not isinstance(profile.get("enabled"), bool):
            raise ValueError("OCR profile enabled must be a boolean")
        runtime = profile.get("runtime")
        if not isinstance(runtime, str) or not runtime.strip() or len(runtime) > 120:
            raise ValueError("OCR profile runtime must contain 1 to 120 characters")
        for field in ("cache_dir", "paddlex_cache_dir"):
            value = profile.get(field)
            if not isinstance(value, str) or not value or len(value) > 1024 or "\x00" in value:
                raise ValueError(f"OCR profile {field} is invalid")
        if not re.fullmatch(r"auto|cpu|gpu:[0-9]{1,2}", str(profile.get("device", "auto"))):
            raise ValueError("OCR profile device is invalid")
        for field in ("detector", "recognizer"):
            component = profile.get(field)
            if not isinstance(component, dict):
                raise ValueError(f"OCR profile {field} must be an object")
            if not isinstance(component.get("model_name"), str) or MODEL_NAME.fullmatch(component["model_name"]) is None:
                raise ValueError(f"OCR profile {field} model_name is invalid")
            if not isinstance(component.get("repository"), str) or REPOSITORY_ID.fullmatch(component["repository"]) is None:
                raise ValueError(f"OCR profile {field} repository is invalid")
        return profile

    def _cache_dir(self, profile: dict[str, Any]) -> Path:
        override = os.environ.get("SITH_HUGGINGFACE_CACHE_DIR")
        if override:
            return Path(override).resolve()
        configured = Path(str(profile.get("cache_dir", ".runtime/huggingface")))
        return configured if configured.is_absolute() else self.root_dir / configured

    def _paddlex_cache_dir(self, profile: dict[str, Any]) -> Path:
        override = os.environ.get("SITH_PADDLEX_CACHE_DIR")
        if override:
            return Path(override).resolve()
        configured = Path(str(profile.get("paddlex_cache_dir", ".runtime/paddlex")))
        return configured if configured.is_absolute() else self.root_dir / configured

    def _model_is_cached(self, cache_dir: Path, repository: str) -> bool:
        namespace = "models--" + repository.replace("/", "--")
        return any((cache_dir / namespace / "snapshots").glob("*/model.safetensors"))

    @staticmethod
    def _paddlex_model_is_cached(cache_dir: Path, model_name: str) -> bool:
        model_names = (model_name, f"{model_name}_safetensors")
        return any((cache_dir / "official_models" / candidate / "model.safetensors").is_file() for candidate in model_names)

    @staticmethod
    def _dependencies_available() -> bool:
        return all(find_spec(package) is not None for package in ("paddleocr", "transformers", "torch"))

    @staticmethod
    def _device(profile: dict[str, Any]) -> str:
        configured = str(profile.get("device", "auto"))
        if configured != "auto":
            return configured
        try:
            import torch

            return "gpu:0" if torch.cuda.is_available() else "cpu"
        except ImportError:
            return "cpu"

    def status(self) -> dict[str, Any]:
        profile = self._profile()
        cache_dir = self._cache_dir(profile)
        paddlex_cache_dir = self._paddlex_cache_dir(profile)
        detector = profile["detector"]
        recognizer = profile["recognizer"]
        detector_cached = self._paddlex_model_is_cached(paddlex_cache_dir, str(detector["model_name"]))
        recognizer_cached = self._paddlex_model_is_cached(paddlex_cache_dir, str(recognizer["model_name"]))
        available = bool(profile.get("enabled")) and self._dependencies_available()
        return {
            "key": "image_ocr",
            "module": "SithAssembly//GlyphWatch",
            "profile": self.PROFILE_ID,
            "state": "available" if available else "not_installed",
            "dependency": "paddleocr + transformers + PyTorch",
            "runtime": str(profile["runtime"]),
            "device": self._device(profile),
            "cache_dir": str(cache_dir),
            "paddlex_cache_dir": str(paddlex_cache_dir),
            "model_download": "preloaded" if detector_cached and recognizer_cached else "missing",
            "models": {
                "detector": {"repository": detector["repository"], "cached": detector_cached},
                "recognizer": {"repository": recognizer["repository"], "cached": recognizer_cached},
            },
            "input": "local JPEG, PNG, GIF or WebP evidence",
        }

    def extract(self, image_path: Path, language: str = "en") -> dict[str, Any]:
        if self.status()["state"] != "available":
            return {
                "state": "not_installed",
                "engine": "PaddleOCR",
                "profile": self.PROFILE_ID,
                "text": "",
                "lines": [],
                "message": "PaddleOCR, Transformers, or PyTorch is not installed. No model was executed.",
            }

        profile = self._profile()
        cache_dir = self._cache_dir(profile)
        paddlex_cache_dir = self._paddlex_cache_dir(profile)
        cache_dir.mkdir(parents=True, exist_ok=True)
        paddlex_cache_dir.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("HF_HOME", str(cache_dir))
        os.environ.setdefault("PADDLE_PDX_CACHE_HOME", str(paddlex_cache_dir))
        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
        from paddleocr import PaddleOCR

        ocr = PaddleOCR(
            text_detection_model_name=str(profile["detector"]["model_name"]),
            text_recognition_model_name=str(profile["recognizer"]["model_name"]),
            engine="transformers",
            device=self._device(profile),
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )
        results = list(ocr.predict(str(image_path)))
        lines = self._extract_lines(results)
        return {
            "state": "completed",
            "engine": "PaddleOCR",
            "profile": self.PROFILE_ID,
            "language_hint": language,
            "text": "\n".join(item["text"] for item in lines),
            "lines": lines,
            "message": "OCR completed for local image evidence.",
        }

    def _extract_lines(self, results: list[Any]) -> list[dict[str, Any]]:
        lines: list[dict[str, Any]] = []
        visited: set[int] = set()
        for result in results:
            payload = self._payload(result)
            self._walk(payload, lines, visited=visited)
            if len(lines) >= MAX_OCR_LINES:
                break
        unique = []
        seen = set()
        text_chars = 0
        for line in lines:
            key = (line["text"], line.get("confidence"))
            if line["text"] and key not in seen:
                if text_chars + len(line["text"]) > MAX_OCR_TEXT_CHARS:
                    break
                unique.append(line)
                seen.add(key)
                text_chars += len(line["text"])
        return unique

    @staticmethod
    def _payload(result: Any) -> Any:
        for method_name in ("json", "to_dict"):
            method = getattr(result, method_name, None)
            if callable(method):
                value = method()
                if isinstance(value, str):
                    try:
                        value = json.loads(value)
                    except json.JSONDecodeError:
                        return value
                return value.get("res", value) if isinstance(value, dict) else value
        return result

    def _walk(
        self,
        value: Any,
        lines: list[dict[str, Any]],
        depth: int = 0,
        visited: set[int] | None = None,
    ) -> None:
        if depth > MAX_OCR_RESULT_DEPTH or len(lines) >= MAX_OCR_LINES:
            return
        visited = visited if visited is not None else set()
        if isinstance(value, (dict, list, tuple)):
            identity = id(value)
            if identity in visited:
                return
            visited.add(identity)
        if isinstance(value, dict):
            texts = value.get("rec_texts")
            scores = value.get("rec_scores") or []
            if isinstance(texts, list):
                for index, text in enumerate(texts):
                    if isinstance(text, str):
                        confidence = scores[index] if index < len(scores) else None
                        lines.append({"text": text.strip()[:MAX_OCR_LINE_CHARS], "confidence": self._number(confidence)})
                        if len(lines) >= MAX_OCR_LINES:
                            return
            for key in ("text", "transcription"):
                text = value.get(key)
                if isinstance(text, str):
                    lines.append({"text": text.strip()[:MAX_OCR_LINE_CHARS], "confidence": self._number(value.get("score") or value.get("confidence"))})
                    if len(lines) >= MAX_OCR_LINES:
                        return
            for child in value.values():
                self._walk(child, lines, depth + 1, visited)
        elif isinstance(value, (list, tuple)):
            for child in value:
                self._walk(child, lines, depth + 1, visited)

    @staticmethod
    def _number(value: Any) -> float | None:
        try:
            return round(float(value), 4)
        except (TypeError, ValueError):
            return None

from __future__ import annotations

from importlib.util import find_spec
import json
from pathlib import Path
from typing import Any


class LocalOcrEngine:
    """Optional PaddleOCR adapter for explicit local image evidence only."""

    def status(self) -> dict[str, Any]:
        available = find_spec("paddleocr") is not None and find_spec("paddle") is not None
        return {
            "key": "image_ocr",
            "module": "SithAssembly//GlyphWatch",
            "profile": "GlyphWatch.PP-OCRv6/1.0",
            "state": "available" if available else "not_installed",
            "dependency": "paddlepaddle + paddleocr",
            "model_download": "explicit per OCR run",
            "input": "local JPEG, PNG, GIF or WebP evidence",
        }

    def extract(self, image_path: Path, language: str = "en") -> dict[str, Any]:
        if self.status()["state"] != "available":
            return {
                "state": "not_installed",
                "engine": "PaddleOCR",
                "profile": "GlyphWatch.PP-OCRv6/1.0",
                "text": "",
                "lines": [],
                "message": "PaddleOCR ist nicht installiert. Kein Modell wurde heruntergeladen oder ausgefuehrt.",
            }

        from paddleocr import PaddleOCR

        ocr = PaddleOCR(
            lang=language,
            ocr_version="PP-OCRv6",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )
        results = list(ocr.predict(str(image_path)))
        lines = self._extract_lines(results)
        return {
            "state": "completed",
            "engine": "PaddleOCR",
            "profile": "GlyphWatch.PP-OCRv6/1.0",
            "text": "\n".join(item["text"] for item in lines),
            "lines": lines,
            "message": "OCR auf dem lokalen Bildbeleg abgeschlossen.",
        }

    def _extract_lines(self, results: list[Any]) -> list[dict[str, Any]]:
        lines: list[dict[str, Any]] = []
        for result in results:
            payload = self._payload(result)
            self._walk(payload, lines)
        unique = []
        seen = set()
        for line in lines:
            key = (line["text"], line.get("confidence"))
            if line["text"] and key not in seen:
                unique.append(line)
                seen.add(key)
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

    def _walk(self, value: Any, lines: list[dict[str, Any]]) -> None:
        if isinstance(value, dict):
            texts = value.get("rec_texts")
            scores = value.get("rec_scores") or []
            if isinstance(texts, list):
                for index, text in enumerate(texts):
                    if isinstance(text, str):
                        confidence = scores[index] if index < len(scores) else None
                        lines.append({"text": text.strip(), "confidence": self._number(confidence)})
            for key in ("text", "transcription"):
                text = value.get(key)
                if isinstance(text, str):
                    lines.append({"text": text.strip(), "confidence": self._number(value.get("score") or value.get("confidence"))})
            for child in value.values():
                self._walk(child, lines)
        elif isinstance(value, (list, tuple)):
            for child in value:
                self._walk(child, lines)

    @staticmethod
    def _number(value: Any) -> float | None:
        try:
            return round(float(value), 4)
        except (TypeError, ValueError):
            return None

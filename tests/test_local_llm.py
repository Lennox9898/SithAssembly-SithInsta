from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.local_llm import LocalLlmBridge, LocalModelRegistry


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None


class LocalLlmTests(unittest.TestCase):
    def test_registry_exposes_disabled_provider_without_secret(self) -> None:
        project_data = Path(__file__).resolve().parent.parent / "data"
        with tempfile.TemporaryDirectory(dir=project_data) as directory:
            path = Path(directory) / "models.json"
            path.write_text(json.dumps({"providers": [{"id": "ollama", "runtime": "Ollama", "enabled": False, "protocol": "ollama_chat", "base_url": "http://127.0.0.1:11434"}], "model_profiles": []}), encoding="utf-8")
            snapshot = LocalModelRegistry(path).snapshot()

        self.assertFalse(snapshot["providers"][0]["enabled"])

    def test_enabled_ollama_request_returns_normalized_readable_content(self) -> None:
        project_data = Path(__file__).resolve().parent.parent / "data"
        with tempfile.TemporaryDirectory(dir=project_data) as directory:
            path = Path(directory) / "models.json"
            path.write_text(
                json.dumps(
                    {
                        "providers": [{"id": "ollama", "runtime": "Ollama", "enabled": True, "protocol": "ollama_chat", "base_url": "http://127.0.0.1:11434", "timeout_seconds": 5, "max_output_tokens": 100}],
                        "model_profiles": [{"id": "qwen", "runtime_models": {"ollama": "qwen3:8b"}, "response_contract": "qwen_evidence_v1"}],
                    }
                ),
                encoding="utf-8",
            )
            bridge = LocalLlmBridge(LocalModelRegistry(path))
            with patch("src.local_llm.urlopen", return_value=FakeResponse({"message": {"content": "Readable output", "thinking": "Reasoning"}, "prompt_eval_count": 2, "eval_count": 3})):
                result = bridge.generate({"provider_id": "ollama", "model_profile": "qwen", "messages": [{"role": "user", "content": "Test"}]})

        self.assertEqual(result["content"], "Readable output")
        self.assertEqual(result["thinking"], "Reasoning")
        self.assertEqual(result["response_contract"], "qwen_evidence_v1")

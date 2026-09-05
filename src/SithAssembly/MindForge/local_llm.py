from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
MESSAGE_ROLES = {"system", "user", "assistant"}


class LocalModelRegistry:
    def __init__(self, registry_path: Path) -> None:
        self.registry_path = registry_path

    def snapshot(self) -> dict[str, Any]:
        registry = self._read()
        return {
            "registry": str(self.registry_path),
            "providers": [self._public_provider(provider) for provider in registry["providers"]],
            "model_profiles": registry["model_profiles"],
        }

    def validate(self) -> dict[str, Any]:
        registry = self._read()
        provider_ids: set[str] = set()
        for provider in registry["providers"]:
            if not isinstance(provider, dict) or not isinstance(provider.get("id"), str) or not provider["id"]:
                raise ValueError("local LLM providers require non-empty string ids")
            if provider["id"] in provider_ids:
                raise ValueError("local LLM provider ids must be unique")
            provider_ids.add(provider["id"])
            self._validate_provider(provider)

        profile_ids: set[str] = set()
        for profile in registry["model_profiles"]:
            if not isinstance(profile, dict) or not isinstance(profile.get("id"), str) or not profile["id"]:
                raise ValueError("local LLM model profiles require non-empty string ids")
            if profile["id"] in profile_ids:
                raise ValueError("local LLM model profile ids must be unique")
            profile_ids.add(profile["id"])
            runtime_models = profile.get("runtime_models", {})
            if not isinstance(runtime_models, dict) or not all(provider_id in provider_ids for provider_id in runtime_models):
                raise ValueError("local LLM model profile references an unknown provider")
        return {"provider_count": len(provider_ids), "model_profile_count": len(profile_ids)}

    def provider(self, provider_id: str) -> dict[str, Any]:
        for provider in self._read()["providers"]:
            if provider.get("id") == provider_id:
                self._validate_provider(provider)
                return provider
        raise ValueError("unknown local LLM provider")

    def profile(self, profile_id: str) -> dict[str, Any]:
        for profile in self._read()["model_profiles"]:
            if profile.get("id") == profile_id:
                return profile
        raise ValueError("unknown local LLM model profile")

    def _read(self) -> dict[str, Any]:
        payload = json.loads(self.registry_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("providers"), list) or not isinstance(payload.get("model_profiles"), list):
            raise ValueError("local model registry requires providers and model_profiles arrays")
        return payload

    @staticmethod
    def _public_provider(provider: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": provider.get("id"),
            "runtime": provider.get("runtime"),
            "enabled": bool(provider.get("enabled")),
            "protocol": provider.get("protocol"),
            "base_url": provider.get("base_url"),
            "timeout_seconds": provider.get("timeout_seconds"),
            "max_output_tokens": provider.get("max_output_tokens"),
        }

    @staticmethod
    def _validate_provider(provider: dict[str, Any]) -> None:
        if provider.get("protocol") not in {"ollama_chat", "openai_chat_completions"}:
            raise ValueError("local LLM provider has an unsupported protocol")
        parsed = urlparse(str(provider.get("base_url", "")))
        if parsed.scheme != "http" or parsed.hostname not in LOOPBACK_HOSTS:
            raise ValueError("local LLM provider must use an HTTP loopback URL")


class LocalLlmBridge:
    """Explicit local LLM requests with normalized readable output."""

    def __init__(self, registry: LocalModelRegistry) -> None:
        self.registry = registry

    def generate(self, request_payload: object) -> dict[str, Any]:
        if not isinstance(request_payload, dict):
            raise ValueError("LLM request must be a JSON object")
        provider = self.registry.provider(str(request_payload.get("provider_id", "")))
        if not provider.get("enabled"):
            raise ValueError("local LLM provider is disabled in the registry")
        profile = self.registry.profile(str(request_payload.get("model_profile", "")))
        runtime_model = profile.get("runtime_models", {}).get(provider["id"])
        if not isinstance(runtime_model, str) or not runtime_model:
            raise ValueError("selected model profile has no runtime model for this provider")
        messages = self._messages(request_payload.get("messages"))
        response = self._request(provider, runtime_model, messages, request_payload)
        return self._normalise_response(provider, profile, runtime_model, response)

    @staticmethod
    def _messages(value: object) -> list[dict[str, str]]:
        if not isinstance(value, list) or not value or len(value) > 64:
            raise ValueError("LLM request requires 1 to 64 messages")
        messages = []
        for message in value:
            if not isinstance(message, dict):
                raise ValueError("LLM messages must be objects")
            role = message.get("role")
            content = message.get("content")
            if role not in MESSAGE_ROLES or not isinstance(content, str) or not content.strip() or len(content) > 32000:
                raise ValueError("LLM messages require a supported role and non-empty content up to 32000 characters")
            messages.append({"role": role, "content": content})
        return messages

    def _request(self, provider: dict[str, Any], runtime_model: str, messages: list[dict[str, str]], request_payload: dict[str, Any]) -> dict[str, Any]:
        maximum = int(provider.get("max_output_tokens", 2048))
        requested = request_payload.get("max_output_tokens", maximum)
        if not isinstance(requested, int):
            raise ValueError("max_output_tokens must be an integer")
        max_output_tokens = max(1, min(requested, maximum))
        temperature = request_payload.get("temperature", 0.2)
        if not isinstance(temperature, (int, float)) or not 0 <= temperature <= 2:
            raise ValueError("temperature must be between 0 and 2")

        if provider["protocol"] == "ollama_chat":
            endpoint = f"{str(provider['base_url']).rstrip('/')}/api/chat"
            body = {"model": runtime_model, "messages": messages, "stream": False, "options": {"temperature": temperature, "num_predict": max_output_tokens}}
        else:
            endpoint = f"{str(provider['base_url']).rstrip('/')}/chat/completions"
            body = {"model": runtime_model, "messages": messages, "temperature": temperature, "max_tokens": max_output_tokens}

        call = Request(endpoint, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urlopen(call, timeout=int(provider.get("timeout_seconds", 120))) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (URLError, OSError, json.JSONDecodeError) as error:
            raise ValueError(f"local LLM request failed: {type(error).__name__}") from error
        if not isinstance(payload, dict):
            raise ValueError("local LLM response must be a JSON object")
        return payload

    @staticmethod
    def _normalise_response(provider: dict[str, Any], profile: dict[str, Any], runtime_model: str, payload: dict[str, Any]) -> dict[str, Any]:
        if provider["protocol"] == "ollama_chat":
            message = payload.get("message", {})
            content = message.get("content", "") if isinstance(message, dict) else ""
            thinking = message.get("thinking", "") if isinstance(message, dict) else ""
            usage = {"prompt_tokens": payload.get("prompt_eval_count"), "output_tokens": payload.get("eval_count"), "total_duration_ns": payload.get("total_duration")}
        else:
            choices = payload.get("choices", [])
            message = choices[0].get("message", {}) if isinstance(choices, list) and choices else {}
            content = message.get("content", "") if isinstance(message, dict) else ""
            thinking = message.get("reasoning_content", "") if isinstance(message, dict) else ""
            usage = payload.get("usage", {})
        if not isinstance(content, str):
            raise ValueError("local LLM response contains no readable content")
        return {
            "provider_id": provider["id"],
            "runtime": provider["runtime"],
            "model_profile": profile["id"],
            "runtime_model": runtime_model,
            "response_contract": profile.get("response_contract", "plain_text"),
            "content": content,
            "thinking": thinking if isinstance(thinking, str) else "",
            "usage": usage,
        }

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
MESSAGE_ROLES = {"system", "user", "assistant"}
MAX_LLM_REQUEST_BYTES = 2 * 1024 * 1024
MAX_LLM_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_LLM_RESPONSE_TEXT_CHARS = 256 * 1024
MAX_MODEL_REGISTRY_BYTES = 512 * 1024
MAX_MODEL_PROVIDERS = 32
MAX_MODEL_PROFILES = 64
REGISTRY_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        return None


def open_local_request(request: Request, timeout: int):
    return build_opener(ProxyHandler({}), _RejectRedirects()).open(request, timeout=timeout)


class LocalModelRegistry:
    def __init__(self, registry_path: Path) -> None:
        self.registry_path = registry_path

    def snapshot(self) -> dict[str, Any]:
        registry = self._validated_registry()
        return {
            "registry": str(self.registry_path),
            "providers": [self._public_provider(provider) for provider in registry["providers"]],
            "model_profiles": [self._public_profile(profile) for profile in registry["model_profiles"]],
        }

    def validate(self) -> dict[str, Any]:
        registry = self._validated_registry()
        return {"provider_count": len(registry["providers"]), "model_profile_count": len(registry["model_profiles"])}

    def _validated_registry(self) -> dict[str, Any]:
        registry = self._read()
        provider_ids: set[str] = set()
        for provider in registry["providers"]:
            if not isinstance(provider, dict) or not self._valid_token(provider.get("id")):
                raise ValueError("local LLM providers require safe string ids")
            if provider["id"] in provider_ids:
                raise ValueError("local LLM provider ids must be unique")
            provider_ids.add(provider["id"])
            self._validate_provider(provider)

        profile_ids: set[str] = set()
        for profile in registry["model_profiles"]:
            if not isinstance(profile, dict) or not self._valid_token(profile.get("id")):
                raise ValueError("local LLM model profiles require safe string ids")
            if profile["id"] in profile_ids:
                raise ValueError("local LLM model profile ids must be unique")
            profile_ids.add(profile["id"])
            self._validate_profile(profile, provider_ids)
        return registry

    def provider(self, provider_id: str) -> dict[str, Any]:
        for provider in self._validated_registry()["providers"]:
            if provider.get("id") == provider_id:
                return provider
        raise ValueError("unknown local LLM provider")

    def profile(self, profile_id: str) -> dict[str, Any]:
        for profile in self._validated_registry()["model_profiles"]:
            if profile.get("id") == profile_id:
                return profile
        raise ValueError("unknown local LLM model profile")

    def _read(self) -> dict[str, Any]:
        if self.registry_path.stat().st_size > MAX_MODEL_REGISTRY_BYTES:
            raise ValueError("local model registry is limited to 512 KB")
        payload = json.loads(self.registry_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("providers"), list) or not isinstance(payload.get("model_profiles"), list):
            raise ValueError("local model registry requires providers and model_profiles arrays")
        if len(payload["providers"]) > MAX_MODEL_PROVIDERS:
            raise ValueError(f"local model registry is limited to {MAX_MODEL_PROVIDERS} providers")
        if len(payload["model_profiles"]) > MAX_MODEL_PROFILES:
            raise ValueError(f"local model registry is limited to {MAX_MODEL_PROFILES} model profiles")
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
    def _public_profile(profile: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": profile["id"],
            "repository": profile.get("repository", ""),
            "kind": profile.get("kind", ""),
            "roles": list(profile.get("roles", [])),
            "response_contract": profile.get("response_contract", "plain_text"),
            "runtime_models": dict(profile["runtime_models"]),
        }

    @staticmethod
    def _valid_token(value: object) -> bool:
        return isinstance(value, str) and REGISTRY_TOKEN.fullmatch(value) is not None

    @staticmethod
    def _validate_provider(provider: dict[str, Any]) -> None:
        if not isinstance(provider.get("runtime"), str) or not provider["runtime"].strip() or len(provider["runtime"].strip()) > 120:
            raise ValueError("local LLM provider runtime must contain 1 to 120 characters")
        if not isinstance(provider.get("enabled"), bool):
            raise ValueError("local LLM provider enabled must be a boolean")
        if provider.get("protocol") not in {"ollama_chat", "openai_chat_completions"}:
            raise ValueError("local LLM provider has an unsupported protocol")
        parsed = urlparse(str(provider.get("base_url", "")))
        if (
            parsed.scheme != "http"
            or parsed.hostname not in LOOPBACK_HOSTS
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("local LLM provider must use an HTTP loopback URL")
        try:
            port = parsed.port
        except ValueError as error:
            raise ValueError("local LLM provider has an invalid port") from error
        if port is not None and not 1 <= port <= 65535:
            raise ValueError("local LLM provider has an invalid port")
        timeout = provider.get("timeout_seconds", 120)
        if not isinstance(timeout, int) or isinstance(timeout, bool) or not 1 <= timeout <= 120:
            raise ValueError("local LLM provider timeout_seconds must be an integer from 1 to 120")
        maximum = provider.get("max_output_tokens", 2048)
        if not isinstance(maximum, int) or isinstance(maximum, bool) or not 1 <= maximum <= 8192:
            raise ValueError("local LLM provider max_output_tokens must be an integer from 1 to 8192")

    @classmethod
    def _validate_profile(cls, profile: dict[str, Any], provider_ids: set[str]) -> None:
        repository = profile.get("repository", "")
        if not isinstance(repository, str) or len(repository) > 512:
            raise ValueError("local LLM model profile repository must contain at most 512 characters")
        kind = profile.get("kind", "")
        if kind and not cls._valid_token(kind):
            raise ValueError("local LLM model profile kind must be a safe string")
        roles = profile.get("roles", [])
        if not isinstance(roles, list) or len(roles) > 32 or not all(cls._valid_token(role) for role in roles):
            raise ValueError("local LLM model profile roles must contain up to 32 safe strings")
        response_contract = profile.get("response_contract", "plain_text")
        if not cls._valid_token(response_contract):
            raise ValueError("local LLM model profile response_contract must be a safe string")
        runtime_models = profile.get("runtime_models")
        if not isinstance(runtime_models, dict) or len(runtime_models) > MAX_MODEL_PROVIDERS:
            raise ValueError("local LLM model profile requires a bounded runtime_models object")
        for provider_id, runtime_model in runtime_models.items():
            if provider_id not in provider_ids:
                raise ValueError("local LLM model profile references an unknown provider")
            if not isinstance(runtime_model, str) or not runtime_model.strip() or len(runtime_model) > 512:
                raise ValueError("local LLM runtime model names must contain 1 to 512 characters")


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
        if not isinstance(requested, int) or isinstance(requested, bool):
            raise ValueError("max_output_tokens must be an integer")
        max_output_tokens = max(1, min(requested, maximum))
        temperature = request_payload.get("temperature", 0.2)
        if not isinstance(temperature, (int, float)) or isinstance(temperature, bool) or not 0 <= temperature <= 2:
            raise ValueError("temperature must be between 0 and 2")

        if provider["protocol"] == "ollama_chat":
            endpoint = f"{str(provider['base_url']).rstrip('/')}/api/chat"
            body = {"model": runtime_model, "messages": messages, "stream": False, "options": {"temperature": temperature, "num_predict": max_output_tokens}}
        else:
            endpoint = f"{str(provider['base_url']).rstrip('/')}/chat/completions"
            body = {"model": runtime_model, "messages": messages, "temperature": temperature, "max_tokens": max_output_tokens}

        encoded_body = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(encoded_body) > MAX_LLM_REQUEST_BYTES:
            raise ValueError("local LLM request is limited to 2 MB")
        call = Request(endpoint, data=encoded_body, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with open_local_request(call, timeout=int(provider.get("timeout_seconds", 120))) as response:
                raw_response = response.read(MAX_LLM_RESPONSE_BYTES + 1)
            if len(raw_response) > MAX_LLM_RESPONSE_BYTES:
                raise ValueError("local LLM response is limited to 4 MB")
            payload = json.loads(raw_response.decode("utf-8"))
        except (URLError, OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
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
        if len(content) > MAX_LLM_RESPONSE_TEXT_CHARS:
            raise ValueError("local LLM response content is too large")
        if not isinstance(thinking, str):
            thinking = ""
        elif len(thinking) > MAX_LLM_RESPONSE_TEXT_CHARS:
            thinking = ""
        return {
            "provider_id": provider["id"],
            "runtime": provider["runtime"],
            "model_profile": profile["id"],
            "runtime_model": runtime_model,
            "response_contract": profile.get("response_contract", "plain_text"),
            "content": content,
            "thinking": thinking,
            "usage": usage,
        }

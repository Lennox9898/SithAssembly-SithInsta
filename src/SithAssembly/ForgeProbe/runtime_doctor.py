from __future__ import annotations

import importlib.metadata
import importlib.util
import json
import platform
import sys
from pathlib import Path
from typing import Any

from src.local_llm import LocalModelRegistry
from src.module_runtime import ModuleRuntime
from src.deployment_preflight import DeploymentPreflight


class RuntimeDoctor:
    """Read-only local diagnostics for the server and optional AI runtimes."""

    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir

    def snapshot(self, compute_mode: str) -> dict[str, Any]:
        acceleration = self._acceleration()
        return {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "compute_mode": compute_mode,
            "acceleration": acceleration,
            "configuration": self.check_configuration(),
            "deployment": DeploymentPreflight(self.root_dir).snapshot(),
            "notes": self._notes(compute_mode, acceleration),
        }

    def check_configuration(self) -> dict[str, Any]:
        checks: list[dict[str, Any]] = []
        module_registry = self.root_dir / "config" / "module_registry.json"
        try:
            runtime = ModuleRuntime(module_registry)
            modules = runtime.startup()
            errors = [module for module in modules if module["state"] == "error"]
            checks.append({"name": "module_registry", "state": "ok" if not errors else "error", "module_count": len(modules), "errors": errors})
        except (OSError, ValueError, json.JSONDecodeError) as error:
            checks.append({"name": "module_registry", "state": "error", "detail": f"{type(error).__name__}: {error}"})

        model_registry = self.root_dir / "config" / "local_model_registry.json"
        try:
            result = LocalModelRegistry(model_registry).validate()
            checks.append({"name": "local_model_registry", "state": "ok", **result})
        except (OSError, ValueError, json.JSONDecodeError) as error:
            checks.append({"name": "local_model_registry", "state": "error", "detail": f"{type(error).__name__}: {error}"})

        for filename in (
            "agent_registry.json",
            "clawdbot.local.json",
            "qwen_response_contract.json",
            "embedded_model_registry.json",
        ):
            try:
                payload = json.loads((self.root_dir / "config" / filename).read_text(encoding="utf-8"))
                state = "ok" if isinstance(payload, dict) else "error"
                if filename == "embedded_model_registry.json":
                    profiles = payload.get("profiles", []) if isinstance(payload, dict) else []
                    state = "ok" if profiles and all(self._valid_embedded_profile(profile) for profile in profiles) else "error"
                checks.append({"name": filename, "state": state})
            except (OSError, json.JSONDecodeError) as error:
                checks.append({"name": filename, "state": "error", "detail": f"{type(error).__name__}: {error}"})
        return {"state": "ok" if all(check["state"] == "ok" for check in checks) else "error", "checks": checks}

    @staticmethod
    def _valid_embedded_profile(profile: Any) -> bool:
        if not isinstance(profile, dict):
            return False
        common = {"id", "module", "runtime", "enabled"}
        if not common <= set(profile):
            return False
        if {"detector", "recognizer"} <= set(profile):
            return {"cache_dir", "paddlex_cache_dir"} <= set(profile)
        if "model_dir" in profile:
            return {"repository", "revision", "output"} <= set(profile)
        return False

    @staticmethod
    def _acceleration() -> dict[str, Any]:
        packages = {name: RuntimeDoctor._package_version(name) for name in ("torch", "xformers", "flash-attn")}
        result: dict[str, Any] = {
            "torch_available": packages["torch"] is not None,
            "xformers_available": packages["xformers"] is not None,
            "flash_attention_available": packages["flash-attn"] is not None,
            "packages": packages,
            "cuda_available": False,
            "cuda_device_count": 0,
            "cuda_version": None,
        }
        if not result["torch_available"]:
            return result
        try:
            import torch

            result.update(
                cuda_available=bool(torch.cuda.is_available()),
                cuda_device_count=int(torch.cuda.device_count()) if torch.cuda.is_available() else 0,
                cuda_version=torch.version.cuda,
            )
        except (ImportError, AttributeError, RuntimeError):
            result["torch_available"] = False
        return result

    @staticmethod
    def _package_version(name: str) -> str | None:
        if importlib.util.find_spec(name.replace("-", "_")) is None:
            return None
        try:
            return importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            return "installed"

    @staticmethod
    def _notes(compute_mode: str, acceleration: dict[str, Any]) -> list[str]:
        notes = ["Diagnostics are read-only; package installation and model downloads are never triggered."]
        if compute_mode == "cuda" and not acceleration["cuda_available"]:
            notes.append("CUDA was requested but is unavailable. The server was not started in CUDA-required mode.")
        if not acceleration["xformers_available"]:
            notes.append("xFormers is not detected. Enable it only after installing a version compatible with the local PyTorch and CUDA build.")
        return notes

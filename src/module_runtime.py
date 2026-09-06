from __future__ import annotations

import importlib
import json
import re
from pathlib import Path
from typing import Any

from src.runtime_logging import RuntimeLogger


# Nested SithAssembly packages are explicitly declared in the local registry.
IMPORT_PATH = re.compile(r"^src\.SithAssembly(?:\.[A-Za-z_][A-Za-z0-9_]*)+$")
MODULE_KEY = re.compile(r"^[a-z][a-z0-9_]{0,79}$")
MAX_REGISTRY_BYTES = 256 * 1024
MAX_MODULES = 64


class ModuleRuntime:
    """Loads only modules explicitly declared in the local registry."""

    def __init__(self, registry_path: Path, logger: RuntimeLogger | None = None) -> None:
        self.registry_path = registry_path
        self.logger = logger
        self.modules: list[dict[str, Any]] = []

    def startup(self) -> list[dict[str, Any]]:
        if self.registry_path.stat().st_size > MAX_REGISTRY_BYTES:
            raise ValueError("module registry is limited to 256 KB")
        payload = json.loads(self.registry_path.read_text(encoding="utf-8"))
        configured = payload.get("modules")
        if not isinstance(configured, list):
            raise ValueError("module registry requires a modules array")
        if len(configured) > MAX_MODULES:
            raise ValueError(f"module registry is limited to {MAX_MODULES} modules")
        keys = [entry.get("key") for entry in configured if isinstance(entry, dict)]
        if len(keys) != len(set(keys)):
            raise ValueError("module registry keys must be unique")

        self.modules = [self._load(entry) for entry in configured]
        if self.logger:
            self.logger.event(
                "module_runtime_started",
                registry=str(self.registry_path),
                loaded=sum(item["state"] == "loaded" for item in self.modules),
                total=len(self.modules),
            )
        return self.modules

    def snapshot(self) -> dict[str, Any]:
        return {
            "registry": str(self.registry_path),
            "loaded": sum(item["state"] == "loaded" for item in self.modules),
            "total": len(self.modules),
            "modules": self.modules,
        }

    def _load(self, entry: object) -> dict[str, Any]:
        if not isinstance(entry, dict):
            return {"key": "unknown", "state": "error", "detail": "registry entry must be an object"}

        key = str(entry.get("key", "unknown"))
        import_path = str(entry.get("import_path", ""))
        enabled_value = entry.get("enabled", False)
        enabled = enabled_value if isinstance(enabled_value, bool) else False
        result: dict[str, Any] = {"key": key, "import_path": import_path, "enabled": enabled}
        if not MODULE_KEY.fullmatch(key):
            result.update(state="error", detail="module key is invalid")
            return result
        if not isinstance(enabled_value, bool):
            result.update(state="error", detail="module enabled must be a boolean")
            return result
        if not enabled:
            result["state"] = "disabled"
            return result
        if not IMPORT_PATH.fullmatch(import_path):
            result.update(state="error", detail="import path is not an allowed src.SithAssembly.* module")
            return result

        try:
            module = importlib.import_module(import_path)
            probe = getattr(module, "runtime_probe", None)
            result["state"] = "loaded"
            if callable(probe):
                probe_result = probe()
                if isinstance(probe_result, dict):
                    result["probe"] = probe_result
        except ModuleNotFoundError as error:
            result.update(state="missing", detail=str(error))
        except Exception as error:  # Module errors must not prevent the local server from starting.
            result.update(state="error", detail=f"{type(error).__name__}: {error}")

        if self.logger:
            self.logger.event("module_runtime_module", key=key, state=result["state"], import_path=import_path)
        return result

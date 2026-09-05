from __future__ import annotations

import importlib
import json
import re
from pathlib import Path
from typing import Any

from src.runtime_logging import RuntimeLogger


# Nested SithAssembly packages are explicitly declared in the local registry.
IMPORT_PATH = re.compile(r"^src(?:\.[A-Za-z_][A-Za-z0-9_]*)+$")


class ModuleRuntime:
    """Loads only modules explicitly declared in the local registry."""

    def __init__(self, registry_path: Path, logger: RuntimeLogger | None = None) -> None:
        self.registry_path = registry_path
        self.logger = logger
        self.modules: list[dict[str, Any]] = []

    def startup(self) -> list[dict[str, Any]]:
        payload = json.loads(self.registry_path.read_text(encoding="utf-8"))
        configured = payload.get("modules")
        if not isinstance(configured, list):
            raise ValueError("module registry requires a modules array")

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
        enabled = bool(entry.get("enabled", False))
        result: dict[str, Any] = {"key": key, "import_path": import_path, "enabled": enabled}
        if not enabled:
            result["state"] = "disabled"
            return result
        if not IMPORT_PATH.fullmatch(import_path):
            result.update(state="error", detail="import path is not an allowed src.* module")
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

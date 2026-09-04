from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any


class DeploymentPreflight:
    """Validates prepared deployment files without starting infrastructure."""

    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir

    def snapshot(self) -> dict[str, Any]:
        checks = [self._config_check(), self._file_check("compose_file", self.root_dir / "deploy" / "compose.yml"), self._file_check("containerfile", self.root_dir / "deploy" / "Containerfile")]
        docker_available = shutil.which("docker") is not None
        checks.append({"name": "docker_cli", "state": "available" if docker_available else "not_found", "detail": "No command is run during preflight."})
        states = {check["state"] for check in checks}
        readiness = "prepared" if "error" not in states else "error"
        return {
            "readiness": readiness,
            "environment": "prepared_local",
            "checks": checks,
            "activation": "blocked_pending_operator_gates",
            "next_command": "docker compose --env-file deploy/.env.example -f deploy/compose.yml config",
        }

    def _config_check(self) -> dict[str, Any]:
        path = self.root_dir / "config" / "deployment.local.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            services = payload.get("services")
            secrets = payload.get("secret_references")
            if not isinstance(services, dict) or not isinstance(secrets, dict):
                raise ValueError("services and secret_references must be objects")
            if not all(isinstance(value, str) and value.startswith("env:") for value in secrets.values()):
                raise ValueError("deployment secret references must use env: names")
            return {"name": "deployment_config", "state": "ok", "service_count": len(services), "secret_reference_count": len(secrets)}
        except (OSError, ValueError, json.JSONDecodeError) as error:
            return {"name": "deployment_config", "state": "error", "detail": f"{type(error).__name__}: {error}"}

    @staticmethod
    def _file_check(name: str, path: Path) -> dict[str, Any]:
        return {"name": name, "state": "ok" if path.is_file() else "error", "path": str(path)}

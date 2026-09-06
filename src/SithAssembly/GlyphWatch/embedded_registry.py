from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


MAX_EMBEDDED_REGISTRY_BYTES = 512 * 1024
MAX_EMBEDDED_PROFILES = 64
PROFILE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,159}$")


class EmbeddedModelRegistry:
    """Bounded loader for the human-editable embedded model registry."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def profile(self, profile_id: str) -> dict[str, Any]:
        if self.path.stat().st_size > MAX_EMBEDDED_REGISTRY_BYTES:
            raise ValueError("embedded model registry is limited to 512 KB")
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("profiles"), list):
            raise ValueError("embedded model registry requires a profiles array")
        profiles = payload["profiles"]
        if len(profiles) > MAX_EMBEDDED_PROFILES:
            raise ValueError(f"embedded model registry is limited to {MAX_EMBEDDED_PROFILES} profiles")

        selected: dict[str, Any] | None = None
        identifiers: set[str] = set()
        for profile in profiles:
            identifier = profile.get("id") if isinstance(profile, dict) else None
            if not isinstance(identifier, str) or PROFILE_ID.fullmatch(identifier) is None:
                raise ValueError("embedded model profiles require safe string ids")
            if identifier in identifiers:
                raise ValueError("embedded model profile ids must be unique")
            identifiers.add(identifier)
            if identifier == profile_id:
                selected = profile
        if selected is None:
            raise ValueError(f"embedded model profile {profile_id} is missing from {self.path}")
        return selected

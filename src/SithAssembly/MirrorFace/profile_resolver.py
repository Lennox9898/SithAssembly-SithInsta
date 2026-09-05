from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProfileChange:
    field: str
    previous: str
    current: str
    confidence: float


class ProfileResolver:
    """Compares recorded profile snapshots without asserting a real-world identity."""

    @staticmethod
    def normalize_handle(handle: str) -> str:
        cleaned = "".join(handle.strip().split())
        if not cleaned:
            return ""
        return cleaned if cleaned.startswith("@") else f"@{cleaned}"

    def compare(self, previous: dict[str, str] | None, current: dict[str, str]) -> list[ProfileChange]:
        if not previous:
            return []
        changes: list[ProfileChange] = []
        for field in ("handle", "display_name", "bio", "profile_url"):
            old = (previous.get(field) or "").strip()
            new = (current.get(field) or "").strip()
            if old and new and old != new:
                confidence = 0.95 if field == "handle" else 0.7
                changes.append(ProfileChange(field, old, new, confidence))
        return changes

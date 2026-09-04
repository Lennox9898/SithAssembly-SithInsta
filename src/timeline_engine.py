from __future__ import annotations

from typing import Any


class TimelineEngine:
    @staticmethod
    def merge(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(events, key=lambda event: (event.get("timestamp", ""), event.get("id", 0)), reverse=True)

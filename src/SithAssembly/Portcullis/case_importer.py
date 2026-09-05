from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ImportPreview:
    accepted: list[dict[str, Any]]
    rejected: list[dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "accepted_count": len(self.accepted),
            "rejected_count": len(self.rejected),
            "rejected": self.rejected,
        }


class CaseImporter:
    """Validates manually supplied or officially exported JSON before local persistence."""

    MAX_ITEMS = 250

    def preview(self, payload: Any) -> ImportPreview:
        items = payload.get("items") if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            raise ValueError("import payload must be a JSON list or an object with an items list")
        if len(items) > self.MAX_ITEMS:
            raise ValueError(f"import is limited to {self.MAX_ITEMS} items")
        accepted: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                rejected.append({"index": index, "reason": "item must be an object"})
                continue
            handle = str(item.get("handle", "")).strip()
            body = str(item.get("body", "")).strip()
            if not handle or not body:
                rejected.append({"index": index, "reason": "handle and body are required"})
                continue
            accepted.append(dict(item))
        return ImportPreview(accepted=accepted, rejected=rejected)

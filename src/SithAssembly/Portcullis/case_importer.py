from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse


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
            if not self._has_safe_urls(item):
                rejected.append({"index": index, "reason": "URLs must use http or https without embedded credentials"})
                continue
            accepted.append(dict(item))
        return ImportPreview(accepted=accepted, rejected=rejected)

    @staticmethod
    def _has_safe_urls(item: dict[str, Any]) -> bool:
        candidates: list[object] = [item.get("source_url")]
        sources = item.get("sources", [])
        if isinstance(sources, list):
            candidates.extend(source.get("url") for source in sources if isinstance(source, dict))
        return all(CaseImporter._is_safe_optional_url(value) for value in candidates)

    @staticmethod
    def _is_safe_optional_url(value: object) -> bool:
        if value is None or not str(value).strip():
            return True
        candidate = str(value).strip()
        if len(candidate) > 2_048 or any(character.isspace() for character in candidate):
            return False
        parsed = urlparse(candidate)
        return parsed.scheme in {"http", "https"} and bool(parsed.hostname) and not parsed.username and not parsed.password

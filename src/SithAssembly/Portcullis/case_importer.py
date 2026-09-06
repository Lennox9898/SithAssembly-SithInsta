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
    MAX_HANDLE_CHARS = 128
    MAX_BODY_CHARS = 100_000

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
            raw_handle = item.get("handle")
            raw_body = item.get("body")
            handle = raw_handle.strip() if isinstance(raw_handle, str) else ""
            body = raw_body.strip() if isinstance(raw_body, str) else ""
            if not handle or len(handle) > self.MAX_HANDLE_CHARS or not body or len(body) > self.MAX_BODY_CHARS:
                rejected.append(
                    {
                        "index": index,
                        "reason": "handle must contain 1 to 128 characters and body must contain 1 to 100000 characters",
                    }
                )
                continue
            if not self._has_safe_urls(item):
                rejected.append({"index": index, "reason": "URLs must use http or https without embedded credentials"})
                continue
            accepted_item = dict(item)
            accepted_item["_import_index"] = index
            accepted.append(accepted_item)
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
        if value is None or value == "":
            return True
        if not isinstance(value, str):
            return False
        candidate = value.strip()
        if len(candidate) > 2_048 or any(
            character.isspace() or ord(character) < 32 or ord(character) == 127
            for character in candidate
        ):
            return False
        parsed = urlparse(candidate)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            return False
        try:
            port = parsed.port
        except ValueError:
            return False
        return port is None or 1 <= port <= 65535

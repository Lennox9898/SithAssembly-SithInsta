from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any


WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class EvidenceFingerprint:
    content_hash: str
    context_hash: str


class EvidenceIntegrity:
    """Creates deterministic local fingerprints; it never fetches or alters source material."""

    def fingerprint_observation(self, payload: dict[str, Any]) -> EvidenceFingerprint:
        body = self._normalize(str(payload.get("body", "")))
        context = {
            "handle": self._normalize(str(payload.get("handle", "")).lower()),
            "platform": self._normalize(str(payload.get("platform", "")).lower()),
            "source_url": self._normalize(str(payload.get("source_url", ""))),
            "captured_at": self._normalize(str(payload.get("captured_at", ""))),
        }
        return EvidenceFingerprint(
            content_hash=self._digest(body),
            context_hash=self._digest(json.dumps(context, sort_keys=True, ensure_ascii=True)),
        )

    @staticmethod
    def payload_hash(payload: Any) -> str:
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
        return EvidenceIntegrity._digest(canonical)

    @staticmethod
    def _normalize(value: str) -> str:
        return WHITESPACE.sub(" ", value.strip()).lower()

    @staticmethod
    def _digest(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


MENTION_PATTERN = re.compile(r"(?<![\w.])@([A-Za-z0-9_.-]{1,64})")
HASHTAG_PATTERN = re.compile(r"(?<!\w)#([\w-]{1,80})", re.UNICODE)
URL_PATTERN = re.compile(r"https?://[^\s<>\]\[\"']+", re.IGNORECASE)


@dataclass(frozen=True)
class CollectedSignals:
    mentions: list[str]
    hashtags: list[str]
    links: list[str]


class Collector:
    """Normalizes analyst-provided public material; it does not crawl platforms."""

    def collect(self, payload: dict[str, Any]) -> CollectedSignals:
        body = str(payload.get("body", ""))
        # A sentence-ending period is not part of an account handle.
        mentions = self._unique([f"@{match.rstrip('.')}" for match in MENTION_PATTERN.findall(body)])
        hashtags = self._unique([f"#{match.lower()}" for match in HASHTAG_PATTERN.findall(body)])
        links = self._unique(URL_PATTERN.findall(body))
        return CollectedSignals(mentions=mentions, hashtags=hashtags, links=links)

    @staticmethod
    def _unique(items: list[str]) -> list[str]:
        return list(dict.fromkeys(items))

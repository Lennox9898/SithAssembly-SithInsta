from __future__ import annotations

from typing import Any


OPENERS = {
    "neutral": "The claim is not supported in this form.",
    "firm": "This is not factually defensible.",
    "sharp": "Plenty of posture, very little evidence.",
}

FLAG_LABELS = {
    "violent_threat": "a threat of violence",
    "dehumanization": "dehumanizing language",
    "recruitment": "recruitment into closed groups",
    "historical_denial": "historical denialism",
    "authoritarian_glorification": "authoritarian glorification",
    "conspiracy": "a conspiracy narrative",
}


def _clean_excerpt(value: str | None, limit: int = 160) -> str:
    if not value:
        return ""
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def compose_draft(observation: dict[str, Any], sources: list[dict[str, Any]], tone: str = "firm") -> dict[str, Any]:
    tone_key = tone if tone in OPENERS else "firm"
    flags = observation.get("danger_flags", [])
    opening = OPENERS[tone_key]

    if not sources:
        return {
            "tone": tone_key,
            "body": "Draft blocked: attach reliable sources before composing a response.",
            "citations": [],
            "state": "blocked_missing_sources",
        }

    signal_clause = (
        "The post uses "
        + ", ".join(FLAG_LABELS.get(flag, flag.replace("_", " ")) for flag in flags[:3])
        + "."
        if flags
        else "The post needs reliable context rather than volume."
    )

    evidence_lines = []
    citations = []
    for index, source in enumerate(sources[:3], start=1):
        title = source["title"]
        excerpt = _clean_excerpt(source.get("excerpt") or title)
        url = source.get("url") or ""
        evidence_lines.append(f"[{index}] {title}: {excerpt}")
        citations.append({"index": index, "title": title, "url": url})

    citation_tail = " ".join(f"[{item['index']}] {item['url']}".strip() for item in citations)
    body = (
        f"{opening} {signal_clause} "
        f"Before repeating myths, consult the sources: "
        f"{' '.join(evidence_lines)} "
        f"Sources: {citation_tail}".strip()
    )

    return {
        "tone": tone_key,
        "body": body,
        "citations": citations,
        "state": "pending_review",
    }

from __future__ import annotations

from typing import Any


OPENERS = {
    "neutral": "Die Behauptung ist so nicht belastbar.",
    "firm": "Das ist sachlich nicht haltbar.",
    "sharp": "Viel Pose, wenig Belege.",
}

FLAG_LABELS = {
    "violent_threat": "Gewaltandrohung",
    "dehumanization": "Entmenschlichung",
    "recruitment": "Rekrutierung in geschlossene Raeume",
    "historical_denial": "Geschichtsrevisionismus",
    "authoritarian_glorification": "autoritaere Verherrlichung",
    "conspiracy": "Verschwoerungsnarrative",
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
            "body": "Entwurf blockiert: Erst belastbare Quellen anhaengen, dann Gegenrede formulieren.",
            "citations": [],
            "state": "blocked_missing_sources",
        }

    signal_clause = (
        "Der Beitrag arbeitet mit "
        + ", ".join(FLAG_LABELS.get(flag, flag.replace("_", " ")) for flag in flags[:3])
        + "."
        if flags
        else "Der Beitrag braucht vor allem belastbaren Kontext statt Lautstaerke."
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
        f"Bevor hier Mythen nachgesprochen werden, lohnt sich der Blick in die Quellen: "
        f"{' '.join(evidence_lines)} "
        f"Quellen: {citation_tail}".strip()
    )

    return {
        "tone": tone_key,
        "body": body,
        "citations": citations,
        "state": "pending_review",
    }

from __future__ import annotations

from dataclasses import dataclass


SIGNAL_PATTERNS = {
    "violent_threat": (
        "hang them",
        "shoot them",
        "cleanse",
        "wipe them out",
    ),
    "dehumanization": (
        "vermin",
        "parasites",
        "subhuman",
        "infestation",
    ),
    "recruitment": (
        "join the channel",
        "join our group",
        "dm for access",
        "private chat",
    ),
    "historical_denial": (
        "history was fabricated",
        "made up atrocity",
        "revisionist truth",
    ),
    "authoritarian_glorification": (
        "strongman rule",
        "purity",
        "traitors must",
        "take the country back",
    ),
    "conspiracy": (
        "globalist plot",
        "replacement",
        "shadow elite",
        "controlled media",
    ),
}

SIGNAL_WEIGHTS = {
    "violent_threat": 40,
    "dehumanization": 25,
    "recruitment": 20,
    "historical_denial": 20,
    "authoritarian_glorification": 15,
    "conspiracy": 10,
}

SEVERITY_LABELS = (
    (0, "niedrig"),
    (20, "moderat"),
    (45, "hoch"),
    (70, "kritisch"),
)


@dataclass(frozen=True)
class AnalysisResult:
    risk_level: int
    severity: str
    danger_flags: list[str]
    summary: str


def _label_for_score(score: int) -> str:
    current = "niedrig"
    for threshold, label in SEVERITY_LABELS:
        if score >= threshold:
            current = label
    return current


def score_text(text: str) -> AnalysisResult:
    lowered = text.casefold()
    matches: list[str] = []
    for signal, patterns in SIGNAL_PATTERNS.items():
        if any(pattern in lowered for pattern in patterns):
            matches.append(signal)

    risk_level = min(100, sum(SIGNAL_WEIGHTS[flag] for flag in matches))
    severity = _label_for_score(risk_level)
    if not matches:
        summary = "Keine direkten Heuristik-Treffer. Menschliche Sichtung bleibt erforderlich."
    else:
        summary = (
            f"Erkannte Signale: {', '.join(matches)}. "
            f"Vorlaeufige Einstufung: {severity} ({risk_level}/100)."
        )

    return AnalysisResult(
        risk_level=risk_level,
        severity=severity,
        danger_flags=matches,
        summary=summary,
    )


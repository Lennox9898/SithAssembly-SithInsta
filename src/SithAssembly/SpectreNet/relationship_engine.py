from __future__ import annotations

from dataclasses import dataclass

from src.collector import CollectedSignals


@dataclass(frozen=True)
class RelationshipFinding:
    target: str
    relation_type: str
    confidence: float


class RelationshipEngine:
    """Produces conservative, evidence-bound links from one captured item."""

    def from_signals(self, signals: CollectedSignals) -> list[RelationshipFinding]:
        findings = [
            RelationshipFinding(target=mention, relation_type="mention", confidence=0.9)
            for mention in signals.mentions
        ]
        findings.extend(
            RelationshipFinding(target=link, relation_type="shared_link", confidence=0.8)
            for link in signals.links
        )
        return findings

    @staticmethod
    def classify_centrality(observation_count: int, degree: int) -> str:
        score = observation_count + degree
        if score >= 8:
            return "central"
        if score >= 4:
            return "recurring"
        return "peripheral"

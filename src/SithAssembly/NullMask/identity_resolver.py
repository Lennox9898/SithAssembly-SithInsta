from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IdentityHypothesis:
    candidate_label: str
    basis: str
    confidence: float
    state: str


class IdentityResolver:
    """Stores analyst-supplied hypotheses only; it never tries to identify a person."""

    def validate(self, candidate_label: str, basis: str, confidence: float, state: str) -> IdentityHypothesis:
        if not candidate_label.strip() or len(candidate_label.strip()) > 500:
            raise ValueError("candidate_label must contain 1 to 500 characters")
        if not basis.strip() or len(basis.strip()) > 20_000:
            raise ValueError("basis must contain 1 to 20000 characters")
        allowed_states = {"unverified", "reviewed", "rejected"}
        if state not in allowed_states:
            raise ValueError("invalid identity claim state")
        return IdentityHypothesis(
            candidate_label=" ".join(candidate_label.split()),
            basis=" ".join(basis.split()),
            confidence=max(0.0, min(float(confidence), 1.0)),
            state=state,
        )

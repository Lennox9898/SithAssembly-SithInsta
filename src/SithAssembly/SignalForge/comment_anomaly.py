from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from importlib.util import find_spec
from math import fabs
import re
from statistics import median
from typing import Any


TOKEN_PATTERN = re.compile(r"[\w-]+", re.UNICODE)
URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)
MENTION_PATTERN = re.compile(r"(?<!\w)@[\w.]+", re.UNICODE)
HASHTAG_PATTERN = re.compile(r"(?<!\w)#[\w-]+", re.UNICODE)


@dataclass(frozen=True)
class AnomalyCandidate:
    observation_id: int
    actor_handle: str
    source_url: str
    score: float
    state: str
    reasons: list[str]
    features: dict[str, float]

    def as_dict(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "actor_handle": self.actor_handle,
            "source_url": self.source_url,
            "score": round(self.score, 3),
            "state": self.state,
            "reasons": self.reasons,
            "features": self.features,
        }


class CommentAnomalyEngine:
    """Scores local comment features and never infers intent or identity."""

    MIN_MODEL_SAMPLES = 20

    def status(self) -> dict[str, Any]:
        available = find_spec("pyod") is not None and find_spec("numpy") is not None
        return {
            "key": "comment_anomaly",
            "module": "SithAssembly//SignalForge",
            "profile": "SignalForge.ECOD/1.0",
            "state": "available" if available else "not_installed",
            "dependency": "pyod + numpy",
            "minimum_samples": self.MIN_MODEL_SAMPLES,
            "fallback": "robust local baseline",
        }

    def analyze(self, observations: list[dict[str, Any]]) -> dict[str, Any]:
        comments = [item for item in observations if "comment" in str(item.get("content_type", "")).lower()]
        if len(comments) < 5:
            return {
                "state": "insufficient_data",
                "method": "none",
                "minimum_samples": 5,
                "sample_count": len(comments),
                "candidates": [],
                "note": "At least five locally captured comments are required for a comparison baseline.",
            }

        features = self._feature_rows(comments)
        rows = [item["features"] for item in features]
        if len(comments) >= self.MIN_MODEL_SAMPLES and self.status()["state"] == "available":
            scores = self._ecod_scores(rows)
            method = "pyod_ecod"
        else:
            scores = self._robust_scores(rows)
            method = "robust_baseline"

        candidates = []
        for item, score in zip(features, scores):
            if score < 0.55:
                continue
            candidates.append(
                AnomalyCandidate(
                    observation_id=int(item["observation_id"]),
                    actor_handle=str(item["actor_handle"]),
                    source_url=str(item.get("source_url") or ""),
                    score=score,
                    state="review_required",
                    reasons=self._reasons(item["features"], rows),
                    features=item["features"],
                ).as_dict()
            )

        candidates.sort(key=lambda item: item["score"], reverse=True)
        return {
            "state": "completed",
            "method": method,
            "sample_count": len(comments),
            "candidates": candidates,
            "note": "Outliers are review candidates, not findings about intent, affiliation, or identity.",
        }

    def _feature_rows(self, observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        actor_counts = Counter(str(item.get("actor_handle", "")).casefold() for item in observations)
        body_counts = Counter(self._normalise_body(str(item.get("body", ""))) for item in observations)
        rows = []
        for observation in observations:
            text = str(observation.get("body", ""))
            tokens = TOKEN_PATTERN.findall(text.casefold())
            alpha = [character for character in text if character.isalpha()]
            features = {
                "characters": float(len(text)),
                "tokens": float(len(tokens)),
                "uppercase_ratio": round(sum(character.isupper() for character in alpha) / max(1, len(alpha)), 3),
                "punctuation_ratio": round(sum(not character.isalnum() and not character.isspace() for character in text) / max(1, len(text)), 3),
                "urls": float(len(URL_PATTERN.findall(text))),
                "mentions": float(len(MENTION_PATTERN.findall(text))),
                "hashtags": float(len(HASHTAG_PATTERN.findall(text))),
                "actor_frequency": float(actor_counts[str(observation.get("actor_handle", "")).casefold()]),
                "duplicate_frequency": float(body_counts[self._normalise_body(text)]),
            }
            rows.append({
                "observation_id": observation["id"],
                "actor_handle": observation["actor_handle"],
                "source_url": observation.get("source_url") or "",
                "features": features,
            })
        return rows

    @staticmethod
    def _normalise_body(text: str) -> str:
        return " ".join(TOKEN_PATTERN.findall(text.casefold()))

    def _robust_scores(self, rows: list[dict[str, float]]) -> list[float]:
        names = tuple(rows[0])
        medians = {name: median(row[name] for row in rows) for name in names}
        mads = {name: median(fabs(row[name] - medians[name]) for row in rows) or 1.0 for name in names}
        scores = []
        for row in rows:
            deviations = sorted((fabs(row[name] - medians[name]) / mads[name] for name in names), reverse=True)
            scores.append(min(1.0, sum(deviations[:3]) / 12.0))
        return scores

    def _ecod_scores(self, rows: list[dict[str, float]]) -> list[float]:
        import numpy as np
        from pyod.models.ecod import ECOD

        matrix = np.array([[row[name] for name in row] for row in rows], dtype=float)
        model = ECOD(contamination=0.1)
        model.fit(matrix)
        raw_scores = list(model.decision_scores_)
        low, high = min(raw_scores), max(raw_scores)
        if high == low:
            return [0.0 for _ in raw_scores]
        return [(float(value) - low) / (high - low) for value in raw_scores]

    def _reasons(self, row: dict[str, float], rows: list[dict[str, float]]) -> list[str]:
        names = tuple(row)
        medians = {name: median(item[name] for item in rows) for name in names}
        mads = {name: median(fabs(item[name] - medians[name]) for item in rows) or 1.0 for name in names}
        ranked = sorted(names, key=lambda name: fabs(row[name] - medians[name]) / mads[name], reverse=True)
        labels = {
            "characters": "ungewoehnliche Laenge",
            "tokens": "ungewoehnliche Tokenzahl",
            "uppercase_ratio": "abweichender Grossbuchstabenanteil",
            "punctuation_ratio": "abweichende Zeichensetzung",
            "urls": "abweichende Linkanzahl",
            "mentions": "abweichende Erwaehnungsanzahl",
            "hashtags": "abweichende Hashtag-Anzahl",
            "actor_frequency": "abweichende Aktivitaetsdichte",
            "duplicate_frequency": "wiederholter Wortlaut",
        }
        return [labels[name] for name in ranked[:3] if fabs(row[name] - medians[name]) / mads[name] >= 2]

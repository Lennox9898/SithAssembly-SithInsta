from __future__ import annotations

from typing import Any

from src.repository import Repository


class CaseManager:
    """Application-facing facade for case work; repository owns SQLite persistence."""

    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    def overview(self, case_id: int) -> dict[str, Any] | None:
        case = self.repository.get_case(case_id)
        if case is None:
            return None
        return {
            "case": case,
            "profiles": self.repository.get_case_profiles(case_id),
            "recent_processing": self.repository.list_processing(case_id)[:6],
        }

    def search(self, case_id: int, filters: dict[str, str]) -> list[dict[str, Any]]:
        return self.repository.list_case_observations(case_id, filters)

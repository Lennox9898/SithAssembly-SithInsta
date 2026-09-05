from __future__ import annotations

from dataclasses import dataclass

from src.assembly_manifest import module_name


@dataclass(frozen=True)
class ProcessingUpdate:
    stage: str
    message: str
    state: str = "completed"
    confidence: float | None = None


class AgentController:
    """Coordinates local analysis stages and exposes them to the review interface."""

    def updates_for_observation(self, relationship_count: int, profile_change_count: int) -> list[ProcessingUpdate]:
        return [
            ProcessingUpdate(module_name("collector"), "Capture normalized; source metadata retained."),
            ProcessingUpdate(module_name("relationship_engine"), f"{relationship_count} evidence-bound links recorded."),
            ProcessingUpdate(module_name("profile_resolver"), f"{profile_change_count} profile changes recorded."),
            ProcessingUpdate(module_name("case_manager"), "Observation added to the case timeline."),
        ]

"""Execution controls for legacy multi-request baselines.

The controls are deliberately outside the copied paper source.  This keeps the
original implementation intact while making large comparison runs bounded and
explicit about early termination.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class LegacyRuntimeConfig:
    mode: str = "bounded"
    max_candidate_paths: int = 3
    max_reallocation_rounds: int = 30
    max_no_improvement_rounds: int = 10
    max_runtime_seconds: float | None = 300.0

    def validate(self) -> None:
        if self.mode not in {"faithful", "bounded", "adapted", "reimplemented"}:
            raise ValueError("mode must be 'faithful', 'bounded', 'adapted' or 'reimplemented'")
        if self.max_candidate_paths < 1:
            raise ValueError("max_candidate_paths must be positive")
        if self.max_reallocation_rounds < 1:
            raise ValueError("max_reallocation_rounds must be positive")
        if self.max_no_improvement_rounds < 1:
            raise ValueError("max_no_improvement_rounds must be positive")
        if self.max_runtime_seconds is not None and self.max_runtime_seconds <= 0:
            raise ValueError("max_runtime_seconds must be positive or None")

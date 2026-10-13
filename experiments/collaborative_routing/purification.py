"""Deterministic Werner-state purification calculations used by the optimizer."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class PurificationPlan:
    rounds: int
    output_fidelity: float
    expected_raw_pairs: float


def success_probability(fidelity: float) -> float:
    """Return the success probability of one nested Werner purification round."""
    _validate_fidelity(fidelity)
    return (
        fidelity ** 2
        + (2.0 / 3.0) * fidelity * (1.0 - fidelity)
        + (5.0 / 9.0) * (1.0 - fidelity) ** 2
    )


def output_fidelity(fidelity: float) -> float:
    """Return the conditional output fidelity of one successful round."""
    probability = success_probability(fidelity)
    return (fidelity ** 2 + (1.0 / 9.0) * (1.0 - fidelity) ** 2) / probability


def fidelity_after_rounds(base_fidelity: float, rounds: int) -> float:
    """Return the conditional fidelity after exactly ``rounds`` successful levels."""
    _validate_fidelity(base_fidelity)
    if rounds < 0:
        raise ValueError("rounds cannot be negative")
    fidelity = base_fidelity
    for _ in range(rounds):
        fidelity = output_fidelity(fidelity)
    return fidelity


def minimum_plan(
    base_fidelity: float,
    required_fidelity: float,
    maximum_rounds: int,
) -> Optional[PurificationPlan]:
    """Find the minimum-round feasible plan and its expected raw-pair cost.

    Returns ``None`` when the target cannot be reached within
    ``maximum_rounds``. Each successful level consumes two outputs from the
    preceding level, while failures are included through the success
    probability denominator.
    """
    _validate_fidelity(base_fidelity)
    _validate_fidelity(required_fidelity)
    if maximum_rounds < 0:
        raise ValueError("maximum_rounds cannot be negative")

    fidelity = base_fidelity
    expected_raw_pairs = 1.0
    if fidelity >= required_fidelity:
        return PurificationPlan(0, fidelity, expected_raw_pairs)

    for round_index in range(1, maximum_rounds + 1):
        expected_raw_pairs *= 2.0 / success_probability(fidelity)
        fidelity = output_fidelity(fidelity)
        if fidelity >= required_fidelity:
            return PurificationPlan(round_index, fidelity, expected_raw_pairs)
    return None


def _validate_fidelity(fidelity: float) -> None:
    if not 0.25 < fidelity <= 1.0:
        raise ValueError("Werner fidelity must be in (0.25, 1]")

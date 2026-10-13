"""Reusable Werner-purification tables for grid-based configuration search."""

from bisect import bisect_left
from dataclasses import dataclass
from functools import lru_cache
from typing import Tuple

from experiments.collaborative_routing.purification import output_fidelity, success_probability


@dataclass(frozen=True)
class PurificationLookupPlan:
    rounds: int
    output_fidelity: float
    expected_raw_pairs: float
    memory_slots_per_endpoint: int


@dataclass(frozen=True)
class PurificationLookupPoint:
    fidelity: float
    plans: Tuple[PurificationLookupPlan, ...]
    output_fidelities: Tuple[float, ...]


def _integer_grid(lower: float, upper: float, step: float) -> Tuple[float, ...]:
    if step <= 0 or upper < lower:
        raise ValueError("invalid fidelity lookup grid")
    count = int(round((upper - lower) / step))
    values = [round(lower + index * step, 12) for index in range(count + 1)]
    if values[-1] < upper - 1e-12:
        values.append(round(upper, 12))
    else:
        values[-1] = round(upper, 12)
    return tuple(values)


@lru_cache(maxsize=32)
def build_werner_purification_lookup(
    lower_fidelity: float,
    upper_fidelity: float,
    fidelity_step: float,
    maximum_rounds: int,
) -> Tuple[PurificationLookupPoint, ...]:
    """Build or reuse a table keyed by range, precision, and purification depth."""
    if maximum_rounds < 0:
        raise ValueError("maximum purification rounds cannot be negative")
    points = []
    for base_fidelity in _integer_grid(
        lower_fidelity,
        upper_fidelity,
        fidelity_step,
    ):
        fidelity = base_fidelity
        expected_raw_pairs = 1.0
        plans = [PurificationLookupPlan(0, fidelity, 1.0, 1)]
        for rounds in range(1, maximum_rounds + 1):
            expected_raw_pairs *= 2.0 / success_probability(fidelity)
            fidelity = output_fidelity(fidelity)
            plans.append(PurificationLookupPlan(
                rounds=rounds,
                output_fidelity=fidelity,
                expected_raw_pairs=expected_raw_pairs,
                memory_slots_per_endpoint=1 << rounds,
            ))
        frozen_plans = tuple(plans)
        points.append(PurificationLookupPoint(
            base_fidelity,
            frozen_plans,
            tuple(plan.output_fidelity for plan in frozen_plans),
        ))
    return tuple(points)


def find_minimum_lookup_plan(
    point: PurificationLookupPoint,
    required_fidelity: float,
) -> PurificationLookupPlan | None:
    """Return the first precomputed purification level satisfying a threshold."""
    index = bisect_left(point.output_fidelities, required_fidelity)
    return point.plans[index] if index < len(point.plans) else None

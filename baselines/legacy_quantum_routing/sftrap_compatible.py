"""Multi-request SFTRAP compatibility adapter for the current resource model.

The published source assumes a single network-wide fidelity threshold.  This
module retains its K-shortest-path pool and adaptive congestion cancellation,
while evaluating purification separately for every request-path-link triple.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import time
from typing import Dict, List

from experiments.collaborative_routing.purification import minimum_plan
from experiments.collaborative_routing.quality_allocation import (
    calculate_end_to_end_fidelity,
    werner_parameter,
)
from experiments.collaborative_routing.throughput_allocation import (
    memory_limited_raw_capacity,
    path_swap_success_probability,
)

from .adapter import BaselineResult
from .runtime import LegacyRuntimeConfig


@dataclass
class _Candidate:
    request_index: int
    path: list
    channels: list
    raw_costs: Dict[object, float]
    achieved_fidelity: float
    rounds: int
    rate: float


def _candidate_paths(scenario, runtime: LegacyRuntimeConfig) -> List[_Candidate]:
    candidates = []
    maximum_rounds = scenario.config.purification.maximum_rounds
    for request_index, request in enumerate(scenario.requests):
        required = float(request.attr["required_fidelity"])
        paths = [
            list(route[2])
            for route in request.attr.get("candidate_routes", [])[:runtime.max_candidate_paths]
        ]
        for path in paths:
            # SFTrap is derived from the purification-enabled iterative
            # routing family. Use QPath's critical-link purification cost for
            # its candidates; the SFTrap-specific part remains path priority
            # and adaptive congestion cancellation below.
            from .paper_reimplemented import _qpath_plan
            qpath_plan = _qpath_plan(
                request, path, maximum_rounds, return_rounds=True
            )
            if qpath_plan is not None:
                qpath_costs, qpath_fidelity, qpath_rounds, rounds_by_channel = qpath_plan
                # Legacy SFTrap updates residual resources with
                # ceil(actual_throughput * (d + 1)), instead of QPath's
                # expected raw-pair cost.  For post-swap rates this becomes
                # (d + 1) / p_swap raw pairs per delivered pair.
                swap_probability = path_swap_success_probability(path)
                sftrap_costs = {
                    channel: (float(rounds_by_channel.get(channel, 0)) + 1.0)
                    / max(swap_probability, 1e-12)
                    for channel in qpath_costs
                }
                candidates.append(_Candidate(
                    request_index=request_index,
                    path=path,
                    channels=list(sftrap_costs),
                    raw_costs=sftrap_costs,
                    achieved_fidelity=qpath_fidelity,
                    rounds=qpath_rounds,
                    rate=0.0,
                ))
                continue
            channels = [left.get_qchannel(right) for left, right in zip(path, path[1:])]
            if any(channel is None for channel in channels):
                continue
            swap_quality = math.prod(
                float(getattr(node, "swap_quality_factor", 1.0))
                for node in path[1:-1]
            )
            request_parameter = werner_parameter(required)
            if swap_quality <= 0 or request_parameter / swap_quality > 1.0:
                continue
            per_link_parameter = (request_parameter / swap_quality) ** (1.0 / len(channels))
            per_link_fidelity = (1.0 + 3.0 * per_link_parameter) / 4.0
            sftrap_rounds = {}
            output_requirements = {}
            rounds = 0
            feasible = True
            for channel in channels:
                plan = minimum_plan(
                    float(getattr(channel, "fidelity")),
                    per_link_fidelity,
                    maximum_rounds,
                )
                if plan is None:
                    feasible = False
                    break
                sftrap_rounds[channel] = plan.rounds
                output_requirements[channel] = plan.output_fidelity
                rounds += plan.rounds
            if not feasible:
                continue
            achieved = calculate_end_to_end_fidelity(path, channels, output_requirements)
            if achieved + 1e-9 < required:
                continue
            swap_probability = path_swap_success_probability(path)
            raw_costs = {
                channel: (float(sftrap_rounds[channel]) + 1.0)
                / max(swap_probability, 1e-12)
                for channel in channels
            }
            candidates.append(_Candidate(
                request_index=request_index,
                path=path,
                channels=channels,
                raw_costs=raw_costs,
                achieved_fidelity=achieved,
                rounds=rounds,
                rate=0.0,
            ))
    return candidates


def _allocate_sftrap_feasible(candidates: List[_Candidate], scenario, runtime: LegacyRuntimeConfig):
    """SFTrap-style path-priority allocation with exact capacity accounting.

    Short paths receive the larger increment. The step is bounded by both
    residual request demand and every shared-link memory capacity, so the
    returned allocation is physically feasible without a destructive final
    projection.
    """
    capacities = {
        channel: memory_limited_raw_capacity(
            channel, float(getattr(channel, "raw_entanglement_rate"))
        )
        for channel in scenario.network.qchannels
    }
    for item in candidates:
        cost = sum(item.raw_costs.values())
        hops = max(1, len(item.path) - 1)
        # SFTrap prioritizes resource-efficient routes. Hop count is only a
        # mild tie-breaker; multiplying by hops made long but low-cost routes
        # unnecessarily unattractive in the previous implementation.
        item._weight = (1.0 + 0.25 / hops) / max(cost, 1e-9)
        item.rate = 0.0
        item._active = True

    iterations = 0
    while iterations < max(1, runtime.max_reallocation_rounds * 10):
        iterations += 1
        active = [item for item in candidates if item._active]
        if not active:
            break
        slopes = {
            channel: sum(item._weight * item.raw_costs.get(channel, 0.0) for item in active)
            for channel in capacities
        }
        steps = [
            capacities[channel] / slope
            for channel, slope in slopes.items()
            if slope > 1e-12
        ]
        for request_index, request in enumerate(scenario.requests):
            current = sum(item.rate for item in candidates if item.request_index == request_index)
            slope = sum(item._weight for item in active if item.request_index == request_index)
            if slope > 1e-12:
                steps.append(
                    max(0.0, float(request.attr["demand_intensity"]) - current) / slope
                )
        if not steps:
            break
        step = min(steps)
        if step <= 1e-12:
            break
        for item in active:
            item.rate += step * item._weight
        for channel, slope in slopes.items():
            capacities[channel] = max(0.0, capacities[channel] - step * slope)
        saturated = {channel for channel, value in capacities.items() if value <= 1e-9}
        for item in active:
            request = scenario.requests[item.request_index]
            current = sum(x.rate for x in candidates if x.request_index == item.request_index)
            if current >= float(request.attr["demand_intensity"]) - 1e-9:
                item._active = False
            elif any(channel in saturated for channel in item.channels):
                item._active = False
    return iterations, "completed"


def _resource_metadata(candidates: List[_Candidate], scenario):
    capacities = {
        channel: memory_limited_raw_capacity(
            channel, float(getattr(channel, "raw_entanglement_rate"))
        )
        for channel in scenario.network.qchannels
    }
    utilizations = []
    for channel, capacity in capacities.items():
        load = sum(item.rate * item.raw_costs.get(channel, 0.0) for item in candidates)
        utilizations.append(load / capacity if capacity > 0 else 0.0)
    return {
        "average_link_utilization": sum(utilizations) / len(utilizations) if utilizations else 0.0,
        "maximum_link_utilization": max(utilizations, default=0.0),
    }


def run_sftrap(scenario, runtime: LegacyRuntimeConfig) -> BaselineResult:
    started = time.perf_counter()
    candidates = _candidate_paths(scenario, runtime)
    iterations, status = _allocate_sftrap_feasible(candidates, scenario, runtime)
    per_request = [0.0] * len(scenario.requests)
    for candidate in candidates:
        per_request[candidate.request_index] += candidate.rate
    return BaselineResult(
        algorithm="SFTrap",
        selected_paths=[[node.name for node in item.path] for item in candidates if item.rate > 0],
        per_request_throughput=per_request,
        total_throughput=sum(per_request),
        accepted_requests=sum(rate > 1e-9 for rate in per_request),
        runtime_seconds=time.perf_counter() - started,
        status=status,
        metadata={
            "iterations": iterations,
            "candidate_paths": len(candidates),
            "per_candidate_fidelity": [item.achieved_fidelity for item in candidates],
            "per_candidate_purification_rounds": [item.rounds for item in candidates],
            "adaptation": "legacy SFTrap residual update: ceil(rate * (rounds + 1))",
            "resource_cost_model": "(purification_rounds + 1) / swap_success_probability",
            **_resource_metadata(candidates, scenario),
        },
    )

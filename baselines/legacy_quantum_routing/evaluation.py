"""Common physical evaluator for fixed legacy multi-request route decisions."""

from __future__ import annotations

import math

from experiments.collaborative_routing.purification import (
    fidelity_after_rounds,
    minimum_plan,
    success_probability,
)
from experiments.collaborative_routing.quality_allocation import (
    calculate_end_to_end_fidelity,
    werner_parameter,
)
from experiments.collaborative_routing.throughput_allocation import (
    memory_limited_raw_capacity,
    path_swap_success_probability,
)


def _expected_raw_pairs(base_fidelity: float, rounds: int) -> float:
    fidelity = base_fidelity
    cost = 1.0
    for _ in range(rounds):
        cost *= 2.0 / success_probability(fidelity)
        fidelity = fidelity_after_rounds(fidelity, 1)
    return cost


def evaluate_legacy_routes(scenario, path_groups, round_groups, weighted=False):
    """Evaluate legacy-selected paths under the shared rate and PF model.

    A legacy algorithm determines which paths and purification counts it wants
    to use.  This evaluator does not replace those decisions; it only applies
    current link generation, shared memory bandwidth and swap probabilities.
    """
    capacities = {
        channel: memory_limited_raw_capacity(
            channel, float(getattr(channel, "raw_entanglement_rate"))
        )
        for channel in scenario.network.qchannels
    }
    name_to_node = {node.name: node for node in scenario.network.nodes}
    candidates = []
    for request_index, request in enumerate(scenario.requests):
        paths = path_groups[request_index] if request_index < len(path_groups) else []
        rounds_for_paths = round_groups[request_index] if request_index < len(round_groups) else []
        for path_index, path_ids in enumerate(paths):
            path = [name_to_node[name] for name in path_ids]
            channels = [left.get_qchannel(right) for left, right in zip(path, path[1:])]
            if any(channel is None for channel in channels):
                continue
            required = float(request.attr["required_fidelity"])
            swap_quality = math.prod(
                float(getattr(node, "swap_quality_factor", 1.0))
                for node in path[1:-1]
            )
            request_parameter = werner_parameter(required)
            if swap_quality <= 0 or request_parameter / swap_quality > 1.0:
                continue
            per_link_parameter = (request_parameter / swap_quality) ** (1.0 / len(channels))
            per_link_fidelity = (1.0 + 3.0 * per_link_parameter) / 4.0
            plans = [
                minimum_plan(
                    float(channel.fidelity),
                    per_link_fidelity,
                    scenario.config.purification.maximum_rounds,
                )
                for channel in channels
            ]
            if any(plan is None for plan in plans):
                continue
            # Legacy round counts are retained when available, but physical
            # feasibility is evaluated with the current minimum feasible plan.
            # This avoids rejecting newly added current-model candidate paths
            # merely because the legacy source did not emit their round vector.
            output_requirements = {
                channel: plan.output_fidelity
                for channel, plan in zip(channels, plans)
            }
            fidelity = calculate_end_to_end_fidelity(path, channels, output_requirements)
            if fidelity + 1e-9 < required:
                continue
            swap_probability = path_swap_success_probability(path)
            if swap_probability <= 0:
                continue
            raw_costs = {
                channel: plan.expected_raw_pairs / swap_probability
                for channel, plan in zip(channels, plans)
            }
            candidates.append({
                "request_index": request_index,
                "path": path,
                "channels": channels,
                "raw_costs": raw_costs,
                "fidelity": fidelity,
                "rate": 0.0,
                "active": True,
            })

    if weighted:
        for item in candidates:
            total_cost = sum(item["raw_costs"].values())
            item["allocation_weight"] = 1.0 / max(total_cost, 1e-9)
    else:
        for item in candidates:
            item["allocation_weight"] = 1.0

    iterations = 0
    while any(item["active"] for item in candidates):
        iterations += 1
        active = [item for item in candidates if item["active"]]
        slopes = {
            channel: sum(item["allocation_weight"] * item["raw_costs"].get(channel, 0.0) for item in active)
            for channel in capacities
        }
        request_slopes = {
            index: sum(item["allocation_weight"] for item in candidates if item["request_index"] == index and item["active"])
            for index in range(len(scenario.requests))
        }
        steps = [
            capacities[channel] / slope
            for channel, slope in slopes.items() if slope > 1e-12
        ]
        for index, request in enumerate(scenario.requests):
            current = sum(item["rate"] for item in candidates if item["request_index"] == index)
            slope = request_slopes[index]
            if slope:
                steps.append(max(0.0, float(request.attr["demand_intensity"]) - current) / slope)
        if not steps:
            break
        step = min(steps)
        if step <= 1e-12:
            break
        for item in active:
            item["rate"] += step * item["allocation_weight"]
        for channel, slope in slopes.items():
            capacities[channel] = max(0.0, capacities[channel] - step * slope)
        saturated = {channel for channel, capacity in capacities.items() if capacity <= 1e-9}
        completed = {
            index for index, request in enumerate(scenario.requests)
            if sum(item["rate"] for item in candidates if item["request_index"] == index)
            >= float(request.attr["demand_intensity"]) - 1e-9
        }
        for item in active:
            if item["request_index"] in completed or any(channel in saturated for channel in item["channels"]):
                item["active"] = False

    per_request = [0.0] * len(scenario.requests)
    for item in candidates:
        per_request[item["request_index"]] += item["rate"]
    return per_request, candidates, iterations

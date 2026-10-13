"""Paper-aligned QLeap/QPath implementations on the current physical model.

The supplied legacy source couples its discrete table depth to a capacity
integer, which is incompatible with the current pairs/s resource model. This
module preserves the algorithmic distinction from the paper while evaluating
all rates with the current Werner, swapping and memory-bandwidth model.
"""

from __future__ import annotations

import math
import time

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


def _path_channels(path):
    return [left.get_qchannel(right) for left, right in zip(path, path[1:])]


def _requirements(request, path):
    required = float(request.attr["required_fidelity"])
    channels = _path_channels(path)
    if any(channel is None for channel in channels):
        return None
    swap_quality = math.prod(float(getattr(node, "swap_quality_factor", 1.0)) for node in path[1:-1])
    target = werner_parameter(required)
    if swap_quality <= 0 or target / swap_quality > 1.0:
        return None
    per_link = (target / swap_quality) ** (1.0 / len(channels))
    fidelity = (1.0 + 3.0 * per_link) / 4.0
    return channels, fidelity


def _qleap_plan(request, path, maximum_rounds):
    resolved = _requirements(request, path)
    if resolved is None:
        return None
    channels, per_link_fidelity = resolved
    plans = [minimum_plan(float(channel.fidelity), per_link_fidelity, maximum_rounds) for channel in channels]
    if any(plan is None for plan in plans):
        return None
    swap_probability = path_swap_success_probability(path)
    if swap_probability <= 0:
        return None
    # Legacy QLeap updates an edge with calactcon(d, n) = n * (d + 1).
    # Keep that linear residual-resource rule, while converting it to a cost
    # per final post-swap pair using the path's limiting purification success.
    from experiments.collaborative_routing.purification import success_probability, output_fidelity
    link_successes = []
    for channel, plan in zip(channels, plans):
        current = float(channel.fidelity)
        success = 1.0
        for _ in range(plan.rounds):
            success *= success_probability(current)
            current = output_fidelity(current)
        link_successes.append(success)
    effective_success = max(min(link_successes, default=1.0), 1e-12)
    raw_costs = {
        channel: (float(plan.rounds) + 1.0)
        / (effective_success * swap_probability)
        for channel, plan in zip(channels, plans)
    }
    achieved = calculate_end_to_end_fidelity(
        path, channels, {channel: plan.output_fidelity for channel, plan in zip(channels, plans)}
    )
    return raw_costs, achieved, sum(plan.rounds for plan in plans)


def _qpath_plan(request, path, maximum_rounds, return_rounds=False):
    """Greedy critical-link purification used by QPath.

    Start with no purification and repeatedly purify the link with the best
    fidelity gain per additional expected raw-pair cost until the end-to-end
    request target is met.
    """
    resolved = _requirements(request, path)
    if resolved is None:
        return None
    channels, _ = resolved
    rounds = {channel: 0 for channel in channels}
    required = float(request.attr["required_fidelity"])
    swap_probability = path_swap_success_probability(path)
    if swap_probability <= 0:
        return None

    def state():
        plans = []
        for channel in channels:
            plan = minimum_plan(float(channel.fidelity), 0.999999, rounds[channel])
            plans.append(plan)
        outputs = {}
        costs = {}
        for channel, plan in zip(channels, plans):
            from experiments.collaborative_routing.purification import fidelity_after_rounds, success_probability
            fidelity = fidelity_after_rounds(float(channel.fidelity), rounds[channel])
            outputs[channel] = fidelity
            cost = 1.0
            current = float(channel.fidelity)
            for _ in range(rounds[channel]):
                cost *= 2.0 / success_probability(current)
                from experiments.collaborative_routing.purification import output_fidelity
                current = output_fidelity(current)
            costs[channel] = cost / swap_probability
        achieved = calculate_end_to_end_fidelity(path, channels, outputs)
        return outputs, costs, achieved

    outputs, selection_costs, achieved = state()
    while achieved + 1e-9 < required:
        best = None
        for channel in channels:
            if rounds[channel] >= maximum_rounds:
                continue
            rounds[channel] += 1
            _, trial_costs, trial_fidelity = state()
            rounds[channel] -= 1
            gain = max(0.0, trial_fidelity - achieved)
            extra = max(1e-9, trial_costs[channel] - selection_costs[channel])
            score = gain / extra
            if best is None or score > best[0]:
                best = (score, channel)
        if best is None or best[0] <= 0:
            return None
        rounds[best[1]] += 1
        outputs, selection_costs, achieved = state()
    # The legacy QPath resource update uses calactcon(n, d) = n * (d + 1).
    # Its exponential 2**d cost is a path-selection priority, not the
    # residual raw-pair deduction. Convert that update to a cost per final
    # (post-swap) delivered pair while retaining the greedy selection above.
    from experiments.collaborative_routing.purification import success_probability
    link_successes = []
    for channel in channels:
        current = float(channel.fidelity)
        success = 1.0
        for _ in range(rounds[channel]):
            success *= success_probability(current)
            from experiments.collaborative_routing.purification import output_fidelity
            current = output_fidelity(current)
        link_successes.append(success)
    effective_success = max(min(link_successes, default=1.0), 1e-12)
    resource_costs = {
        channel: (float(rounds[channel]) + 1.0)
        / (effective_success * swap_probability)
        for channel in channels
    }
    if return_rounds:
        return resource_costs, achieved, sum(rounds.values()), rounds
    return resource_costs, achieved, sum(rounds.values())


def _candidate_pool(scenario, algorithm, runtime):
    candidates = []
    for request_index, request in enumerate(scenario.requests):
        routes = request.attr.get("candidate_routes", [])[:runtime.max_candidate_paths]
        for rank, route in enumerate(routes):
            path = list(route[2])
            plan = (_qpath_plan if algorithm == "QPath" else _qleap_plan)(
                request, path, scenario.config.purification.maximum_rounds
            )
            if plan is None:
                continue
            raw_costs, fidelity, rounds = plan
            candidates.append({
                "request_index": request_index,
                "path": path,
                "channels": list(raw_costs),
                "raw_costs": raw_costs,
                "rate": 0.0,
                "active": True,
                "rank": rank,
                "fidelity": fidelity,
                "rounds": rounds,
            })
    return candidates


def _resource_metadata(candidates, scenario):
    capacities = {
        channel: memory_limited_raw_capacity(
            channel, float(getattr(channel, "raw_entanglement_rate"))
        )
        for channel in scenario.network.qchannels
    }
    utilizations = []
    for channel, capacity in capacities.items():
        load = sum(item["rate"] * item["raw_costs"].get(channel, 0.0) for item in candidates)
        utilizations.append(load / capacity if capacity > 0 else 0.0)
    return {
        "average_link_utilization": sum(utilizations) / len(utilizations) if utilizations else 0.0,
        "maximum_link_utilization": max(utilizations, default=0.0),
    }


def run_reimplemented(scenario, algorithm, runtime: LegacyRuntimeConfig):
    started = time.perf_counter()
    candidates = _candidate_pool(scenario, algorithm, runtime)
    capacities = {
        channel: memory_limited_raw_capacity(channel, float(getattr(channel, "raw_entanglement_rate")))
        for channel in scenario.network.qchannels
    }
    # Low-cost and high-priority paths receive more of the progressive-fill
    # increment, while every candidate remains available to a request.
    for item in candidates:
        item["weight"] = 1.0 / ((1.0 + item["rank"]) * max(1e-9, sum(item["raw_costs"].values())))
    for _ in range(max(1, runtime.max_reallocation_rounds)):
        active = [item for item in candidates if item["active"]]
        if not active:
            break
        slopes = {
            channel: sum(item["weight"] * item["raw_costs"].get(channel, 0.0) for item in active)
            for channel in capacities
        }
        steps = [capacities[channel] / slope for channel, slope in slopes.items() if slope > 1e-12]
        for index, request in enumerate(scenario.requests):
            current = sum(item["rate"] for item in candidates if item["request_index"] == index)
            slope = sum(item["weight"] for item in active if item["request_index"] == index)
            if slope:
                steps.append(max(0.0, float(request.attr["demand_intensity"]) - current) / slope)
        if not steps:
            break
        step = min(steps)
        if step <= 1e-12:
            break
        for item in active:
            item["rate"] += step * item["weight"]
        for channel, slope in slopes.items():
            capacities[channel] = max(0.0, capacities[channel] - step * slope)
        saturated = {channel for channel, capacity in capacities.items() if capacity <= 1e-9}
        for item in active:
            request = scenario.requests[item["request_index"]]
            current = sum(x["rate"] for x in candidates if x["request_index"] == item["request_index"])
            if current >= float(request.attr["demand_intensity"]) - 1e-9 or any(channel in saturated for channel in item["channels"]):
                item["active"] = False
    rates = [sum(item["rate"] for item in candidates if item["request_index"] == index) for index in range(len(scenario.requests))]
    return BaselineResult(
        algorithm=algorithm,
        selected_paths=[[node.name for node in item["path"]] for item in candidates if item["rate"] > 1e-9],
        per_request_throughput=rates,
        total_throughput=sum(rates),
        accepted_requests=sum(rate > 1e-9 for rate in rates),
        runtime_seconds=time.perf_counter() - started,
        metadata={
            "implementation": "paper-aligned",
            "candidate_paths": len(candidates),
            **_resource_metadata(candidates, scenario),
        },
    )

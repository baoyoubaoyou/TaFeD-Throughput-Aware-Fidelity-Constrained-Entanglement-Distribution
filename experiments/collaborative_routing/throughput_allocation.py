"""End-to-end entanglement-rate allocation on fixed configured paths.

This module implements the Progressive Filling (PF) resource allocator used
as one of the ER baselines in the INFOCOM 2025 SPFD paper.  Link configuration
is treated as fixed.  Purification happens before swapping, so one delivered
end-to-end pair consumes ``eta_r,e / psi_r`` raw pairs on every traversed link,
where ``eta_r,e`` includes purification failures and ``psi_r`` is the success
probability of all swapping operations on the path.
"""

from dataclasses import dataclass, field
import math
from typing import Dict, List, Mapping, Optional

from qns.entity.node.node import QNode
from qns.entity.qchannel.qchannel import QuantumChannel
from qns.network.requests import Request

from experiments.collaborative_routing.configuration_models import (
    LinkConfigurationResult,
)
from experiments.collaborative_routing.quality_models import QualityAllocationResult


@dataclass
class RequestThroughputAllocation:
    """PF allocation and physical costs for one end-to-end request."""

    request: Request
    demand_rate: float
    allocated_rate: float
    path: List[QNode]
    channels: List[QuantumChannel]
    swap_success_probability: float
    link_raw_costs: Dict[QuantumChannel, float]
    bottleneck_links: List[QuantumChannel] = field(default_factory=list)
    failure_reason: Optional[str] = None

    @property
    def demand_satisfaction(self) -> float:
        if self.demand_rate <= 0:
            return 0.0
        return min(1.0, self.allocated_rate / self.demand_rate)

    @property
    def fully_satisfied(self) -> bool:
        return self.allocated_rate + 1e-9 >= self.demand_rate


@dataclass
class LinkThroughputAllocation:
    """Raw EPR capacity consumed by all requests on one physical link."""

    channel: QuantumChannel
    raw_capacity: float
    raw_consumed: float
    residual_capacity: float
    request_raw_consumption: Dict[int, float]

    @property
    def utilization(self) -> float:
        if self.raw_capacity <= 0:
            return 0.0
        return min(1.0, self.raw_consumed / self.raw_capacity)


@dataclass
class EndToEndThroughputResult:
    """End-to-end rates and link resource usage returned by PF."""

    request_allocations: Dict[int, RequestThroughputAllocation]
    link_allocations: Dict[QuantumChannel, LinkThroughputAllocation]
    iterations: int

    @property
    def total_edr(self) -> float:
        return sum(item.allocated_rate for item in self.request_allocations.values())

    @property
    def minimum_request_edr(self) -> float:
        rates = [item.allocated_rate for item in self.request_allocations.values()]
        return min(rates, default=0.0)

    @property
    def average_request_edr(self) -> float:
        rates = [item.allocated_rate for item in self.request_allocations.values()]
        return sum(rates) / len(rates) if rates else 0.0

    @property
    def demand_satisfaction_ratio(self) -> float:
        total_demand = sum(
            item.demand_rate for item in self.request_allocations.values()
        )
        return self.total_edr / total_demand if total_demand > 0 else 0.0

    @property
    def fully_satisfied_requests(self) -> int:
        return sum(
            item.fully_satisfied for item in self.request_allocations.values()
        )

    @property
    def request_acceptance_rate(self) -> float:
        if not self.request_allocations:
            return 0.0
        return self.fully_satisfied_requests / len(self.request_allocations)

    @property
    def average_link_utilization(self) -> float:
        values = [item.utilization for item in self.link_allocations.values()]
        return sum(values) / len(values) if values else 0.0

    @property
    def maximum_link_utilization(self) -> float:
        return max(
            (item.utilization for item in self.link_allocations.values()),
            default=0.0,
        )


def path_swap_success_probability(path: List[QNode]) -> float:
    """Return the success probability of all swaps on a fixed path."""
    probability = 1.0
    for node in path[1:-1]:
        node_probability = float(
            getattr(node, "swap_success_probability", 1.0)
        )
        if not 0.0 < node_probability <= 1.0:
            raise ValueError(f"invalid swapping success probability on {node}")
        probability *= node_probability
    return probability


def memory_limited_raw_capacity(channel: QuantumChannel, generated_rate: float) -> float:
    """Apply the channel's equal-share endpoint memory-bandwidth limit."""
    memory_rate = float(getattr(channel, "memory_bandwidth", float("inf")))
    return min(float(generated_rate), memory_rate)


def _request_paths(
    quality_result: QualityAllocationResult,
) -> Dict[int, tuple[Request, List[QNode], List[QuantumChannel]]]:
    paths = {}
    for request_plan in quality_result.request_plans:
        selected = request_plan.selected_plan
        if selected is not None:
            paths[id(request_plan.request)] = (
                request_plan.request,
                list(selected.path),
                list(selected.channels),
            )
    return paths


def _purification_costs(
    configuration_result: LinkConfigurationResult,
) -> Dict[tuple[int, QuantumChannel], float]:
    costs = {}
    for channel, decision in configuration_result.decisions.items():
        selected = decision.selected
        if selected is None:
            continue
        for request_decision in selected.request_decisions:
            costs[(id(request_decision.request), channel)] = float(
                request_decision.expected_raw_pairs
            )
    return costs


def _prepare_requests(
    quality_result: QualityAllocationResult,
    configuration_result: LinkConfigurationResult,
    include_swapping_failures: bool,
    request_link_raw_costs: Optional[
        Mapping[int, Mapping[QuantumChannel, float]]
    ] = None,
) -> Dict[int, RequestThroughputAllocation]:
    paths = _request_paths(quality_result)
    purification_costs = _purification_costs(configuration_result)
    allocations = {}
    for request_plan in quality_result.request_plans:
        request = request_plan.request
        request_key = id(request)
        demand_rate = float(request.attr["demand_intensity"])
        if demand_rate < 0:
            raise ValueError("request demand intensity cannot be negative")
        if request_key not in paths:
            allocations[request_key] = RequestThroughputAllocation(
                request=request,
                demand_rate=demand_rate,
                allocated_rate=0.0,
                path=[],
                channels=[],
                swap_success_probability=0.0,
                link_raw_costs={},
                failure_reason="request does not have a feasible fixed path",
            )
            continue

        _, path, channels = paths[request_key]
        swap_probability = (
            path_swap_success_probability(path) if include_swapping_failures else 1.0
        )
        missing = [
            channel for channel in channels
            if (request_key, channel) not in purification_costs
            or configuration_result.decisions.get(channel) is None
            or configuration_result.decisions[channel].selected is None
        ]
        if missing:
            allocations[request_key] = RequestThroughputAllocation(
                request=request,
                demand_rate=demand_rate,
                allocated_rate=0.0,
                path=path,
                channels=channels,
                swap_success_probability=swap_probability,
                link_raw_costs={},
                failure_reason="one or more path links lack a feasible configuration",
            )
            continue

        default_costs = {
            channel: purification_costs[(request_key, channel)]
            / swap_probability
            for channel in channels
        }
        if request_link_raw_costs is not None:
            supplied = request_link_raw_costs.get(request_key)
            if supplied is None or any(channel not in supplied for channel in channels):
                allocations[request_key] = RequestThroughputAllocation(
                    request=request,
                    demand_rate=demand_rate,
                    allocated_rate=0.0,
                    path=path,
                    channels=channels,
                    swap_success_probability=swap_probability,
                    link_raw_costs={},
                    failure_reason="request has no feasible swapping-tree costs",
                )
                continue
            default_costs = {
                channel: float(supplied[channel]) for channel in channels
            }
            if any(cost <= 0 or not math.isfinite(cost) for cost in default_costs.values()):
                raise ValueError("tree-specific raw costs must be finite and positive")

        allocations[request_key] = RequestThroughputAllocation(
            request=request,
            demand_rate=demand_rate,
            allocated_rate=0.0,
            path=path,
            channels=channels,
            swap_success_probability=swap_probability,
            link_raw_costs=default_costs,
        )
    return allocations


def progressive_fill_end_to_end_throughput(
    quality_result: QualityAllocationResult,
    configuration_result: LinkConfigurationResult,
    include_swapping_failures: bool = True,
    request_link_raw_costs: Optional[
        Mapping[int, Mapping[QuantumChannel, float]]
    ] = None,
    tolerance: float = 1e-9,
    mutate_requests: bool = True,
) -> EndToEndThroughputResult:
    """Allocate max-min fair end-to-end EDR on fixed paths.

    Every unfrozen request is raised at the same rate until either its demand
    is met or a traversed link is saturated.  A request frozen by a bottleneck
    never consumes more than its fair share, while requests on other links can
    continue increasing.
    """
    if tolerance <= 0:
        raise ValueError("tolerance must be positive")
    requests = _prepare_requests(
        quality_result,
        configuration_result,
        include_swapping_failures,
        request_link_raw_costs=request_link_raw_costs,
    )
    capacities = {
        channel: memory_limited_raw_capacity(channel, decision.selected.raw_rate)
        for channel, decision in configuration_result.decisions.items()
        if decision.selected is not None
    }
    residual = dict(capacities)
    active = {
        request_key
        for request_key, item in requests.items()
        if item.failure_reason is None and item.demand_rate > tolerance
    }
    iterations = 0

    while active:
        iterations += 1
        link_slopes = {
            channel: sum(
                requests[request_key].link_raw_costs.get(channel, 0.0)
                for request_key in active
            )
            for channel in capacities
        }
        link_steps = {
            channel: max(0.0, residual[channel]) / slope
            for channel, slope in link_slopes.items()
            if slope > tolerance
        }
        demand_steps = {
            request_key: max(
                0.0,
                requests[request_key].demand_rate
                - requests[request_key].allocated_rate,
            )
            for request_key in active
        }
        candidates = list(link_steps.values()) + list(demand_steps.values())
        if not candidates:
            break
        step = min(candidates)
        if not math.isfinite(step):
            raise ValueError("non-finite progressive-filling step")

        if step > tolerance:
            for request_key in active:
                requests[request_key].allocated_rate += step
            for channel, slope in link_slopes.items():
                residual[channel] = max(
                    0.0,
                    residual[channel] - step * slope,
                )

        saturated = {
            channel
            for channel, slope in link_slopes.items()
            if slope > tolerance and residual[channel] <= tolerance
        }
        completed = {
            request_key
            for request_key in active
            if requests[request_key].demand_rate
            - requests[request_key].allocated_rate <= tolerance
        }
        bottlenecked = {
            request_key
            for request_key in active
            if any(
                channel in saturated
                for channel in requests[request_key].channels
            )
        }
        for request_key in bottlenecked:
            requests[request_key].bottleneck_links = [
                channel
                for channel in requests[request_key].channels
                if channel in saturated
            ]
        frozen = completed | bottlenecked
        if not frozen:
            raise RuntimeError("progressive filling made no progress")
        active.difference_update(frozen)

    link_allocations = {}
    for channel, capacity in capacities.items():
        request_consumption = {
            request_key: item.allocated_rate * item.link_raw_costs[channel]
            for request_key, item in requests.items()
            if channel in item.link_raw_costs
        }
        consumed = sum(request_consumption.values())
        if consumed > capacity + max(tolerance, capacity * 1e-9):
            raise RuntimeError(
                f"progressive filling exceeded capacity on {channel}: "
                f"{consumed} > {capacity}"
            )
        link_allocations[channel] = LinkThroughputAllocation(
            channel=channel,
            raw_capacity=capacity,
            raw_consumed=min(capacity, consumed),
            residual_capacity=max(0.0, capacity - consumed),
            request_raw_consumption=request_consumption,
        )

    result = EndToEndThroughputResult(requests, link_allocations, iterations)
    if mutate_requests:
        for item in requests.values():
            item.request.attr["end_to_end_throughput"] = item.allocated_rate
            item.request.attr["throughput_demand_satisfaction"] = (
                item.demand_satisfaction
            )
            item.request.attr["path_swap_success_probability"] = (
                item.swap_success_probability
            )
            item.request.attr["throughput_bottleneck_links"] = [
                channel.name for channel in item.bottleneck_links
            ]
    return result


def allocate_spfd_end_to_end_throughput(
    spfd_result,
    include_swapping_failures: bool = True,
    mutate_requests: bool = True,
) -> EndToEndThroughputResult:
    """Convenience wrapper connecting SPFD's two stages to PF routing."""
    return progressive_fill_end_to_end_throughput(
        spfd_result.quality_result,
        spfd_result.configuration_result,
        include_swapping_failures=include_swapping_failures,
        mutate_requests=mutate_requests,
    )


def allocate_stage_one_end_to_end_throughput(
    stage_one_result,
    include_swapping_failures: bool = True,
    mutate_requests: bool = True,
) -> EndToEndThroughputResult:
    """Apply the same PF allocator to the joint algorithm's selected record."""
    selected = stage_one_result.selected_record
    return progressive_fill_end_to_end_throughput(
        selected.quality_result,
        selected.configuration_result,
        include_swapping_failures=include_swapping_failures,
        mutate_requests=mutate_requests,
    )

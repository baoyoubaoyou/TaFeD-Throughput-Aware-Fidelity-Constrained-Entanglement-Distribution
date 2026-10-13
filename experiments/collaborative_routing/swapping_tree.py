"""Congestion-aware optimal swapping trees on fixed quantum paths."""

from dataclasses import dataclass, field
import math
from typing import Dict, List, Mapping, Optional, Tuple

from qns.entity.node.node import QNode
from qns.entity.qchannel.qchannel import QuantumChannel
from qns.network.requests import Request

from experiments.collaborative_routing.configuration_models import (
    LinkConfigurationResult,
)
from experiments.collaborative_routing.quality_models import QualityAllocationResult
from experiments.collaborative_routing.throughput_allocation import (
    EndToEndThroughputResult,
    progressive_fill_end_to_end_throughput,
)


@dataclass(frozen=True)
class SwappingTreeConfig:
    """Controls for tree/resource alternating optimization."""

    maximum_iterations: int = 10
    relative_improvement_tolerance: float = 0.01
    congestion_epsilon: float = 0.05
    price_smoothing: float = 0.5
    saturation_tolerance: float = 1e-9

    def validate(self) -> None:
        if self.maximum_iterations < 1:
            raise ValueError("maximum swapping-tree iterations must be positive")
        if not 0 <= self.relative_improvement_tolerance < 1:
            raise ValueError("relative improvement tolerance must be in [0, 1)")
        if self.congestion_epsilon <= 0:
            raise ValueError("congestion epsilon must be positive")
        if not 0 < self.price_smoothing <= 1:
            raise ValueError("price smoothing must be in (0, 1]")
        if self.saturation_tolerance <= 0:
            raise ValueError("saturation tolerance must be positive")


@dataclass
class SwappingTreeNode:
    """One interval in an ordered binary swapping tree."""

    left_index: int
    right_index: int
    split_index: Optional[int] = None
    left: Optional["SwappingTreeNode"] = None
    right: Optional["SwappingTreeNode"] = None

    @property
    def is_leaf(self) -> bool:
        return self.right_index == self.left_index + 1

    def signature(self):
        if self.is_leaf:
            return self.left_index
        return (
            self.split_index,
            self.left.signature(),
            self.right.signature(),
        )


@dataclass
class RequestSwappingTree:
    request: Request
    path: List[QNode]
    channels: List[QuantumChannel]
    root: SwappingTreeNode
    weighted_cost: float
    amplification_factors: Dict[QuantumChannel, float]
    raw_costs: Dict[QuantumChannel, float]

    @property
    def signature(self):
        return self.root.signature()


@dataclass
class SwappingTreeIterationRecord:
    iteration: int
    trees: Dict[int, RequestSwappingTree]
    throughput_result: EndToEndThroughputResult
    link_prices: Dict[QuantumChannel, float]
    trees_unchanged: bool
    relative_total_edr_change: Optional[float]


@dataclass
class SwappingTreeOptimizationResult:
    records: List[SwappingTreeIterationRecord]
    converged: bool
    stop_reason: str

    @property
    def iterations(self) -> int:
        return len(self.records)

    @property
    def final_record(self) -> SwappingTreeIterationRecord:
        if not self.records:
            raise ValueError("swapping-tree optimization did not run")
        return self.records[-1]

    @property
    def best_record(self) -> SwappingTreeIterationRecord:
        """Select the max-min-fair history best, then maximize total EDR."""
        return max(
            self.records,
            key=lambda record: (
                record.throughput_result.minimum_request_edr,
                record.throughput_result.total_edr,
                record.throughput_result.demand_satisfaction_ratio,
            ),
        )

    @property
    def selected_record(self) -> SwappingTreeIterationRecord:
        return self.final_record if self.converged else self.best_record


def _request_purification_costs(
    quality_result: QualityAllocationResult,
    configuration_result: LinkConfigurationResult,
) -> Dict[int, Tuple[Request, List[QNode], List[QuantumChannel], Dict[QuantumChannel, float]]]:
    costs = {}
    for request_plan in quality_result.request_plans:
        selected_plan = request_plan.selected_plan
        if selected_plan is None:
            continue
        request = request_plan.request
        per_link = {}
        feasible = True
        for channel in selected_plan.channels:
            decision = configuration_result.decisions.get(channel)
            if decision is None or decision.selected is None:
                feasible = False
                break
            request_decision = next(
                (
                    item for item in decision.selected.request_decisions
                    if item.request is request
                ),
                None,
            )
            if request_decision is None:
                feasible = False
                break
            per_link[channel] = float(request_decision.expected_raw_pairs)
        if not feasible:
            # The request is retained by PF as a zero-throughput allocation.
            continue
        costs[id(request)] = (
            request,
            list(selected_plan.path),
            list(selected_plan.channels),
            per_link,
        )
    return costs


def optimize_request_swapping_tree(
    request: Request,
    path: List[QNode],
    channels: List[QuantumChannel],
    purification_costs: Mapping[QuantumChannel, float],
    link_prices: Mapping[QuantumChannel, float],
) -> RequestSwappingTree:
    """Solve the ordered binary-tree problem exactly by interval DP."""
    hop_count = len(channels)
    if len(path) != hop_count + 1 or hop_count < 1:
        raise ValueError("path and channel sequence are inconsistent")
    cost: Dict[Tuple[int, int], float] = {}
    split: Dict[Tuple[int, int], int] = {}
    for index, channel in enumerate(channels):
        price = float(link_prices[channel])
        eta = float(purification_costs[channel])
        if price <= 0 or eta <= 0:
            raise ValueError("link prices and purification costs must be positive")
        cost[(index, index + 1)] = price * eta

    for length in range(2, hop_count + 1):
        for left_index in range(0, hop_count - length + 1):
            right_index = left_index + length
            choices = []
            for split_index in range(left_index + 1, right_index):
                probability = float(
                    getattr(path[split_index], "swap_success_probability", 1.0)
                )
                if not 0 < probability <= 1:
                    raise ValueError(
                        f"invalid swapping success probability on {path[split_index]}"
                    )
                candidate = (
                    cost[(left_index, split_index)]
                    + cost[(split_index, right_index)]
                ) / probability
                choices.append((candidate, split_index))
            best_cost, best_split = min(choices, key=lambda item: (item[0], item[1]))
            cost[(left_index, right_index)] = best_cost
            split[(left_index, right_index)] = best_split

    def build(left_index: int, right_index: int) -> SwappingTreeNode:
        if right_index == left_index + 1:
            return SwappingTreeNode(left_index, right_index)
        split_index = split[(left_index, right_index)]
        return SwappingTreeNode(
            left_index=left_index,
            right_index=right_index,
            split_index=split_index,
            left=build(left_index, split_index),
            right=build(split_index, right_index),
        )

    root = build(0, hop_count)
    amplification = {channel: 1.0 for channel in channels}

    def propagate(node: SwappingTreeNode, ancestor_factor: float) -> None:
        if node.is_leaf:
            amplification[channels[node.left_index]] = ancestor_factor
            return
        probability = float(
            getattr(path[node.split_index], "swap_success_probability", 1.0)
        )
        next_factor = ancestor_factor / probability
        propagate(node.left, next_factor)
        propagate(node.right, next_factor)

    propagate(root, 1.0)
    raw_costs = {
        channel: purification_costs[channel] * amplification[channel]
        for channel in channels
    }
    return RequestSwappingTree(
        request=request,
        path=path,
        channels=channels,
        root=root,
        weighted_cost=cost[(0, hop_count)],
        amplification_factors=amplification,
        raw_costs=raw_costs,
    )


def build_fixed_request_swapping_tree(
    request: Request,
    path: List[QNode],
    channels: List[QuantumChannel],
    purification_costs: Mapping[QuantumChannel, float],
    link_prices: Mapping[QuantumChannel, float],
    strategy: str = "left_deep",
) -> RequestSwappingTree:
    """Build a deterministic non-optimized tree for controlled comparisons.

    ``left_deep`` swaps an increasingly long prefix with the next link.  It is
    the strict tree equivalent of conventional source-to-destination sequential
    swapping, and is therefore a fair baseline for the interval-DP optimum.
    """
    hop_count = len(channels)
    if len(path) != hop_count + 1 or hop_count < 1:
        raise ValueError("path and channel sequence are inconsistent")
    if strategy != "left_deep":
        raise ValueError("only the left_deep fixed-tree strategy is supported")

    def build(left_index: int, right_index: int) -> SwappingTreeNode:
        if right_index == left_index + 1:
            return SwappingTreeNode(left_index, right_index)
        split_index = right_index - 1
        return SwappingTreeNode(
            left_index=left_index,
            right_index=right_index,
            split_index=split_index,
            left=build(left_index, split_index),
            right=build(split_index, right_index),
        )

    root = build(0, hop_count)
    amplification = {channel: 1.0 for channel in channels}

    def propagate(node: SwappingTreeNode, ancestor_factor: float) -> None:
        if node.is_leaf:
            amplification[channels[node.left_index]] = ancestor_factor
            return
        probability = float(
            getattr(path[node.split_index], "swap_success_probability", 1.0)
        )
        if not 0 < probability <= 1:
            raise ValueError(
                f"invalid swapping success probability on {path[node.split_index]}"
            )
        next_factor = ancestor_factor / probability
        propagate(node.left, next_factor)
        propagate(node.right, next_factor)

    propagate(root, 1.0)
    raw_costs = {
        channel: float(purification_costs[channel]) * amplification[channel]
        for channel in channels
    }
    weighted_cost = sum(
        float(link_prices[channel]) * raw_costs[channel]
        for channel in channels
    )
    return RequestSwappingTree(
        request=request,
        path=path,
        channels=channels,
        root=root,
        weighted_cost=weighted_cost,
        amplification_factors=amplification,
        raw_costs=raw_costs,
    )


def allocate_fixed_swapping_tree_throughput(
    quality_result: QualityAllocationResult,
    configuration_result: LinkConfigurationResult,
    strategy: str = "left_deep",
    mutate_requests: bool = False,
) -> Tuple[Dict[int, RequestSwappingTree], EndToEndThroughputResult]:
    """Build fixed trees for all requests and run the common PF allocator."""
    request_data = _request_purification_costs(
        quality_result,
        configuration_result,
    )
    prices = _initial_link_prices(configuration_result)
    trees = {
        request_key: build_fixed_request_swapping_tree(
            request,
            path,
            channels,
            purification_costs,
            prices,
            strategy=strategy,
        )
        for request_key, (
            request,
            path,
            channels,
            purification_costs,
        ) in request_data.items()
    }
    throughput = progressive_fill_end_to_end_throughput(
        quality_result,
        configuration_result,
        include_swapping_failures=False,
        request_link_raw_costs={
            request_key: tree.raw_costs
            for request_key, tree in trees.items()
        },
        mutate_requests=mutate_requests,
    )
    return trees, throughput


def _initial_link_prices(
    configuration_result: LinkConfigurationResult,
) -> Dict[QuantumChannel, float]:
    capacities = {
        channel: float(decision.selected.raw_rate)
        for channel, decision in configuration_result.decisions.items()
        if decision.selected is not None
    }
    maximum = max(capacities.values(), default=1.0)
    return {
        channel: maximum / max(capacity, 1e-12)
        for channel, capacity in capacities.items()
    }


def _update_congestion_prices(
    old_prices: Mapping[QuantumChannel, float],
    throughput_result: EndToEndThroughputResult,
    config: SwappingTreeConfig,
) -> Dict[QuantumChannel, float]:
    updated = {}
    for channel, allocation in throughput_result.link_allocations.items():
        target = config.congestion_epsilon + 1.0 / max(
            1.0 - allocation.utilization,
            config.congestion_epsilon,
        )
        updated[channel] = (
            (1.0 - config.price_smoothing) * old_prices[channel]
            + config.price_smoothing * target
        )
    return updated


def _tree_signature(trees: Mapping[int, RequestSwappingTree]):
    return {request_key: tree.signature for request_key, tree in trees.items()}


def optimize_swapping_trees_and_throughput(
    quality_result: QualityAllocationResult,
    configuration_result: LinkConfigurationResult,
    config: SwappingTreeConfig = SwappingTreeConfig(),
    mutate_requests: bool = True,
) -> SwappingTreeOptimizationResult:
    """Alternate exact per-request tree DP and global PF allocation."""
    config.validate()
    request_data = _request_purification_costs(
        quality_result,
        configuration_result,
    )
    prices = _initial_link_prices(configuration_result)
    records = []
    previous_signature = None
    previous_total_edr = None
    converged = False
    stop_reason = "maximum_iterations"

    for iteration in range(1, config.maximum_iterations + 1):
        trees = {}
        for request_key, (
            request, path, channels, purification_costs,
        ) in request_data.items():
            tree = optimize_request_swapping_tree(
                request, path, channels, purification_costs, prices
            )
            trees[request_key] = tree
        throughput = progressive_fill_end_to_end_throughput(
            quality_result,
            configuration_result,
            include_swapping_failures=False,
            request_link_raw_costs={
                request_key: tree.raw_costs
                for request_key, tree in trees.items()
            },
            tolerance=config.saturation_tolerance,
            mutate_requests=False,
        )
        signature = _tree_signature(trees)
        trees_unchanged = (
            previous_signature is not None and signature == previous_signature
        )
        relative_change = None
        if previous_total_edr is not None:
            relative_change = abs(
                throughput.total_edr - previous_total_edr
            ) / max(abs(previous_total_edr), config.saturation_tolerance)
        records.append(SwappingTreeIterationRecord(
            iteration=iteration,
            trees=trees,
            throughput_result=throughput,
            link_prices=dict(prices),
            trees_unchanged=trees_unchanged,
            relative_total_edr_change=relative_change,
        ))
        if trees_unchanged or (
            relative_change is not None
            and relative_change <= config.relative_improvement_tolerance
        ):
            converged = True
            stop_reason = (
                "trees_unchanged" if trees_unchanged else "small_edr_change"
            )
            break
        prices = _update_congestion_prices(prices, throughput, config)
        previous_signature = signature
        previous_total_edr = throughput.total_edr

    result = SwappingTreeOptimizationResult(records, converged, stop_reason)
    if mutate_requests:
        selected = result.selected_record
        for request_key, tree in selected.trees.items():
            request = tree.request
            allocation = selected.throughput_result.request_allocations[request_key]
            request.attr["swapping_tree"] = tree.root
            request.attr["swapping_tree_signature"] = tree.signature
            request.attr["swapping_amplification_factors"] = {
                channel.name: factor
                for channel, factor in tree.amplification_factors.items()
            }
            request.attr["end_to_end_throughput"] = allocation.allocated_rate
            request.attr["throughput_demand_satisfaction"] = (
                allocation.demand_satisfaction
            )
            request.attr["throughput_bottleneck_links"] = [
                channel.name for channel in allocation.bottleneck_links
            ]
    return result


def optimize_spfd_swapping_trees(
    spfd_result,
    config: SwappingTreeConfig = SwappingTreeConfig(),
    mutate_requests: bool = True,
) -> SwappingTreeOptimizationResult:
    return optimize_swapping_trees_and_throughput(
        spfd_result.quality_result,
        spfd_result.configuration_result,
        config=config,
        mutate_requests=mutate_requests,
    )


def optimize_stage_one_swapping_trees(
    stage_one_result,
    config: SwappingTreeConfig = SwappingTreeConfig(),
    mutate_requests: bool = True,
) -> SwappingTreeOptimizationResult:
    selected = stage_one_result.selected_record
    return optimize_swapping_trees_and_throughput(
        selected.quality_result,
        selected.configuration_result,
        config=config,
        mutate_requests=mutate_requests,
    )

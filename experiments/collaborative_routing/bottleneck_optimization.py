"""PF-bottleneck-aware refinement of fidelity allocation and link configuration.

Swapping order is deliberately fixed to the conventional left-deep sequence.
This module refines the existing joint algorithm using only three additions:
PF-derived congestion prices, weak-request-aware configuration scoring, and
configuration re-search restricted to actual bottleneck links.
"""

from dataclasses import dataclass
import math
from time import perf_counter
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from qns.entity.qchannel.qchannel import QuantumChannel

from experiments.collaborative_routing.configuration_models import (
    LinkConfigurationDecision,
    LinkConfigurationEvaluation,
    LinkConfigurationResult,
)
from experiments.collaborative_routing.link_configuration import (
    collect_link_requirements,
    evaluate_lookup_configuration,
    evaluate_lookup_configurations,
)
from experiments.collaborative_routing.purification_lookup import (
    PurificationLookupPoint,
    build_werner_purification_lookup,
)
from experiments.collaborative_routing.quality_allocation import (
    allocate_fixed_path_qualities,
    store_quality_allocation_result,
)
from experiments.collaborative_routing.quality_models import QualityAllocationResult
from experiments.collaborative_routing.stage_one import (
    build_relaxed_quality_result,
    run_stage_one,
)
from experiments.collaborative_routing.swapping_tree import (
    RequestSwappingTree,
    allocate_fixed_swapping_tree_throughput,
)
from experiments.collaborative_routing.throughput_allocation import (
    EndToEndThroughputResult,
)


@dataclass(frozen=True)
class BottleneckOptimizationConfig:
    maximum_refinement_iterations: int = 15
    price_smoothing: float = 0.3
    congestion_epsilon: float = 0.05
    softmin_temperature_fraction: float = 0.25
    bottom_request_fraction: float = 0.25
    utilization_threshold: float = 0.90
    fidelity_relaxation: float = 0.25
    retained_configuration_candidates: int = 3
    no_best_improvement_patience: int = 3
    relative_improvement_tolerance: float = 0.005

    def validate(self) -> None:
        if self.maximum_refinement_iterations < 1:
            raise ValueError("maximum refinement iterations must be positive")
        if not 0 < self.price_smoothing <= 1:
            raise ValueError("price smoothing must be in (0, 1]")
        if self.congestion_epsilon <= 0:
            raise ValueError("congestion epsilon must be positive")
        if self.softmin_temperature_fraction <= 0:
            raise ValueError("soft-min temperature fraction must be positive")
        if not 0 < self.bottom_request_fraction <= 1:
            raise ValueError("bottom request fraction must be in (0, 1]")
        if not 0 < self.utilization_threshold <= 1:
            raise ValueError("utilization threshold must be in (0, 1]")
        if not 0 < self.fidelity_relaxation <= 1:
            raise ValueError("fidelity relaxation must be in (0, 1]")
        if self.retained_configuration_candidates < 1:
            raise ValueError("at least one configuration candidate is required")
        if self.no_best_improvement_patience < 1:
            raise ValueError("patience must be positive")


@dataclass
class BottleneckIterationRecord:
    iteration: int
    quality_result: QualityAllocationResult
    configuration_result: LinkConfigurationResult
    fixed_trees: Dict[int, RequestSwappingTree]
    throughput_result: EndToEndThroughputResult
    quality_prices: Dict[QuantumChannel, float]
    bottleneck_channels: List[QuantumChannel]
    evaluated_configuration_candidates: int


@dataclass
class BottleneckStageOneResult:
    base_stage_one_result: object
    records: List[BottleneckIterationRecord]
    converged: bool
    stop_reason: str
    base_runtime_seconds: float
    refinement_runtime_seconds: float

    @property
    def refinement_iterations(self) -> int:
        return max(0, len(self.records) - 1)

    @property
    def best_record(self) -> BottleneckIterationRecord:
        return max(
            self.records,
            key=lambda record: _objective_key(record.throughput_result),
        )

    @property
    def selected_record(self) -> BottleneckIterationRecord:
        return self.best_record


def _jain(values: Sequence[float]) -> float:
    denominator = len(values) * sum(value * value for value in values)
    return sum(values) ** 2 / denominator if denominator > 0 else 0.0


def _objective_key(result: EndToEndThroughputResult) -> Tuple[float, float, float]:
    rates = [item.allocated_rate for item in result.request_allocations.values()]
    return result.minimum_request_edr, result.total_edr, _jain(rates)


def _fidelity_signature(
    quality_result: QualityAllocationResult,
) -> Dict[Tuple[int, QuantumChannel], float]:
    return {
        (id(request_plan.request), channel): fidelity
        for request_plan in quality_result.request_plans
        if request_plan.selected_plan is not None
        for channel, fidelity in request_plan.selected_plan.fidelity_requirements.items()
    }


def _active_channels(quality_result, network) -> List[QuantumChannel]:
    active = {
        channel
        for request_plan in quality_result.request_plans
        if request_plan.selected_plan is not None
        for channel in request_plan.selected_plan.channels
    }
    return [channel for channel in network.qchannels if channel in active]


def weak_request_weights(
    throughput: EndToEndThroughputResult,
    config: BottleneckOptimizationConfig,
) -> Dict[int, float]:
    """Smooth max-min weights, avoiding a discontinuous single-request price."""
    allocations = throughput.request_allocations
    if not allocations:
        return {}
    rates = [item.allocated_rate for item in allocations.values()]
    minimum = min(rates)
    mean = sum(rates) / len(rates)
    temperature = max(
        config.congestion_epsilon,
        config.softmin_temperature_fraction * max(mean, 1.0),
    )
    raw = {
        request_key: math.exp(
            -min(700.0, max(0.0, item.allocated_rate - minimum) / temperature)
        )
        for request_key, item in allocations.items()
    }
    total = sum(raw.values())
    return {key: value / total for key, value in raw.items()}


def identify_bottleneck_channels(
    throughput: EndToEndThroughputResult,
    config: BottleneckOptimizationConfig,
) -> List[QuantumChannel]:
    """Return only links relevant to congested and lowest-throughput requests."""
    allocations = sorted(
        throughput.request_allocations.values(),
        key=lambda item: item.allocated_rate,
    )
    if not allocations:
        return []
    bottom_count = max(
        1, math.ceil(len(allocations) * config.bottom_request_fraction)
    )
    bottom = allocations[:bottom_count]
    minimum = allocations[0].allocated_rate
    minimum_requests = [
        item for item in allocations
        if item.allocated_rate <= minimum + 1e-9
    ]
    channels = {
        channel
        for item in bottom
        for channel in item.bottleneck_links
    }
    channels.update(
        channel
        for item in minimum_requests
        for channel in item.channels
    )
    channels.update(
        channel
        for channel, link in throughput.link_allocations.items()
        if link.utilization >= config.utilization_threshold
        and any(channel in item.channels for item in bottom)
    )
    return [
        channel for channel in throughput.link_allocations
        if channel in channels
    ]


def update_pf_bottleneck_prices(
    previous_prices: Mapping[QuantumChannel, float],
    throughput: EndToEndThroughputResult,
    fixed_trees: Mapping[int, RequestSwappingTree],
    config: BottleneckOptimizationConfig,
) -> Dict[QuantumChannel, float]:
    """Use PF utilization, weak-request weights, and actual raw costs."""
    weights = weak_request_weights(throughput, config)
    raw_targets = {}
    for channel, link in throughput.link_allocations.items():
        weighted_cost = sum(
            weights.get(request_key, 0.0)
            * tree.raw_costs.get(channel, 0.0)
            for request_key, tree in fixed_trees.items()
        )
        bottleneck_weight = sum(
            weights.get(request_key, 0.0)
            for request_key, item in throughput.request_allocations.items()
            if channel in item.bottleneck_links
        )
        congestion = link.utilization / max(
            1.0 - link.utilization + config.congestion_epsilon,
            config.congestion_epsilon,
        )
        raw_targets[channel] = (
            congestion * weighted_cost * (1.0 + bottleneck_weight)
        )

    mean_old = (
        sum(previous_prices.values()) / len(previous_prices)
        if previous_prices else 1.0
    )
    positive = [value for value in raw_targets.values() if value > 0]
    mean_raw = sum(positive) / len(positive) if positive else 1.0
    floor = 0.1 * mean_old
    updated = {}
    for channel, raw_target in raw_targets.items():
        target = max(floor, mean_old * raw_target / mean_raw)
        old = previous_prices.get(channel, mean_old)
        updated[channel] = (
            (1.0 - config.price_smoothing) * old
            + config.price_smoothing * target
        )
    return updated


def _nearest_point(
    fidelity: float,
    lookup: Sequence[PurificationLookupPoint],
) -> PurificationLookupPoint:
    return min(lookup, key=lambda point: abs(point.fidelity - fidelity))


def _configuration_score(
    evaluation: LinkConfigurationEvaluation,
    request_weights: Mapping[int, float],
    previous_trees: Mapping[int, RequestSwappingTree],
) -> Tuple[float, float, float]:
    weighted_cost = 0.0
    weight_sum = 0.0
    for item in evaluation.request_decisions:
        request_key = id(item.request)
        weight = request_weights.get(request_key, 0.0)
        tree = previous_trees.get(request_key)
        amplification = (
            tree.amplification_factors.get(evaluation.channel, 1.0)
            if tree is not None else 1.0
        )
        weighted_cost += weight * item.expected_raw_pairs * amplification
        weight_sum += weight
    if weight_sum <= 0 or weighted_cost <= 0:
        fair_capacity = evaluation.effective_rate
    else:
        fair_capacity = evaluation.raw_rate * weight_sum / weighted_cost
    return (
        fair_capacity,
        -evaluation.total_purification_rounds,
        -evaluation.fidelity,
    )


def _decision(
    channel: QuantumChannel,
    selected: Optional[LinkConfigurationEvaluation],
    evaluated_count: int,
    feasible_count: int,
) -> LinkConfigurationDecision:
    return LinkConfigurationDecision(
        channel=channel,
        selected=selected,
        evaluated_count=evaluated_count,
        feasible_count=feasible_count,
    )


def select_bottleneck_configurations(
    quality_result: QualityAllocationResult,
    previous_configuration: LinkConfigurationResult,
    previous_throughput: EndToEndThroughputResult,
    previous_trees: Mapping[int, RequestSwappingTree],
    bottleneck_channels: Sequence[QuantumChannel],
    scenario,
    config: BottleneckOptimizationConfig,
) -> Tuple[
    LinkConfigurationResult,
    Dict[int, RequestSwappingTree],
    EndToEndThroughputResult,
    int,
]:
    """Re-search only bottleneck links and verify top candidates with PF."""
    requirements = collect_link_requirements(quality_result)
    lookup = build_werner_purification_lookup(
        scenario.config.links.minimum_fidelity,
        scenario.config.links.maximum_fidelity,
        scenario.config.link_configuration_search.fine_step,
        scenario.config.purification.maximum_rounds,
    )
    bottleneck_set = set(bottleneck_channels)
    request_weights = weak_request_weights(previous_throughput, config)
    decisions = {}
    candidate_map = {}
    evaluated_count = 0

    for channel, channel_requirements in requirements.items():
        old_decision = previous_configuration.decisions.get(channel)
        old_selected = old_decision.selected if old_decision is not None else None
        old_evaluation = None
        if old_selected is not None:
            old_evaluation = evaluate_lookup_configuration(
                channel,
                channel_requirements,
                _nearest_point(old_selected.fidelity, lookup),
            )
            evaluated_count += 1
            if not old_evaluation.feasible:
                old_evaluation = None

        if channel not in bottleneck_set:
            if old_evaluation is None:
                evaluations = evaluate_lookup_configurations(
                    channel, channel_requirements, lookup
                )
                evaluated_count += len(evaluations)
                feasible = [item for item in evaluations if item.feasible]
                old_evaluation = max(
                    feasible,
                    key=lambda item: item.effective_rate,
                    default=None,
                )
                decisions[channel] = _decision(
                    channel, old_evaluation, len(evaluations), len(feasible)
                )
            else:
                decisions[channel] = _decision(channel, old_evaluation, 1, 1)
            continue

        evaluations = evaluate_lookup_configurations(
            channel, channel_requirements, lookup
        )
        evaluated_count += len(evaluations)
        feasible = [item for item in evaluations if item.feasible]
        ranked = sorted(
            feasible,
            key=lambda item: _configuration_score(
                item, request_weights, previous_trees
            ),
            reverse=True,
        )
        candidates = ranked[:config.retained_configuration_candidates]
        if old_evaluation is not None:
            candidates.append(old_evaluation)
        candidates = list({item.fidelity: item for item in candidates}.values())
        selected = old_evaluation or (candidates[0] if candidates else None)
        decisions[channel] = _decision(
            channel, selected, len(evaluations), len(feasible)
        )
        candidate_map[channel] = candidates

    current_configuration = LinkConfigurationResult(decisions)
    current_trees, current_throughput = allocate_fixed_swapping_tree_throughput(
        quality_result, current_configuration, mutate_requests=False
    )

    for channel in bottleneck_channels:
        candidates = candidate_map.get(channel, [])
        trials = []
        for evaluation in candidates:
            trial_decisions = dict(current_configuration.decisions)
            existing = trial_decisions[channel]
            trial_decisions[channel] = _decision(
                channel,
                evaluation,
                existing.evaluated_count,
                existing.feasible_count,
            )
            trial_configuration = LinkConfigurationResult(trial_decisions)
            trial_trees, trial_throughput = allocate_fixed_swapping_tree_throughput(
                quality_result, trial_configuration, mutate_requests=False
            )
            evaluated_count += 1
            trials.append((
                _objective_key(trial_throughput),
                trial_configuration,
                trial_trees,
                trial_throughput,
            ))
        if trials:
            _, current_configuration, current_trees, current_throughput = max(
                trials, key=lambda item: item[0]
            )
    return (
        current_configuration,
        current_trees,
        current_throughput,
        evaluated_count,
    )


def _activate_configuration(result: LinkConfigurationResult) -> None:
    for channel, decision in result.decisions.items():
        if decision.selected is None:
            continue
        channel.fidelity = decision.selected.fidelity
        channel.raw_entanglement_rate = decision.selected.raw_rate
        channel.bandwidth = decision.selected.raw_rate
        channel.selected_configuration = decision.selected


def run_bottleneck_optimized_stage_one(
    scenario,
    config: BottleneckOptimizationConfig = BottleneckOptimizationConfig(),
    mutate_requests: bool = True,
) -> BottleneckStageOneResult:
    """Refine the legacy Joint result using the three bottleneck-aware steps."""
    config.validate()
    started = perf_counter()
    base_result = run_stage_one(scenario)
    base_runtime = perf_counter() - started
    refinement_started = perf_counter()
    base = base_result.selected_record
    quality = base.quality_result
    configuration = base.configuration_result
    trees, throughput = allocate_fixed_swapping_tree_throughput(
        quality, configuration, mutate_requests=False
    )
    active_channels = _active_channels(quality, scenario.network)
    previous_fidelities = _fidelity_signature(quality)
    prices = update_pf_bottleneck_prices(
        {
            channel: state.quality_price
            for channel, state in quality.link_states.items()
        },
        throughput,
        trees,
        config,
    )
    bottlenecks = identify_bottleneck_channels(throughput, config)
    records = [BottleneckIterationRecord(
        0, quality, configuration, trees, throughput, dict(prices),
        bottlenecks, 0,
    )]
    best_primary = throughput.minimum_request_edr
    rounds_without_best_improvement = 0
    converged = False
    stop_reason = "maximum_refinement_iterations"

    for iteration in range(1, config.maximum_refinement_iterations + 1):
        raw_quality = allocate_fixed_path_qualities(
            scenario.network,
            requests=scenario.requests,
            maximum_purification_rounds=scenario.config.purification.maximum_rounds,
            solver_config=scenario.config.quality_allocation,
            quality_prices=prices,
            active_channels=active_channels,
            mutate_requests=False,
        )
        quality = build_relaxed_quality_result(
            raw_quality, previous_fidelities, config.fidelity_relaxation
        )
        (
            configuration,
            trees,
            throughput,
            evaluated,
        ) = select_bottleneck_configurations(
            quality,
            configuration,
            records[-1].throughput_result,
            records[-1].fixed_trees,
            bottlenecks,
            scenario,
            config,
        )
        prices = update_pf_bottleneck_prices(
            prices, throughput, trees, config
        )
        bottlenecks = identify_bottleneck_channels(throughput, config)
        previous_fidelities = _fidelity_signature(quality)
        records.append(BottleneckIterationRecord(
            iteration, quality, configuration, trees, throughput,
            dict(prices), bottlenecks, evaluated,
        ))

        relative_best_improvement = (
            throughput.minimum_request_edr - best_primary
        ) / max(abs(best_primary), 1e-9)
        if relative_best_improvement > config.relative_improvement_tolerance:
            best_primary = throughput.minimum_request_edr
            rounds_without_best_improvement = 0
        else:
            rounds_without_best_improvement += 1
        if rounds_without_best_improvement >= config.no_best_improvement_patience:
            converged = True
            stop_reason = "no_best_minimum_edr_improvement"
            break

    result = BottleneckStageOneResult(
        base_result,
        records,
        converged,
        stop_reason,
        base_runtime,
        perf_counter() - refinement_started,
    )
    if mutate_requests:
        selected = result.selected_record
        store_quality_allocation_result(selected.quality_result)
        _activate_configuration(selected.configuration_result)
        for request_key, tree in selected.fixed_trees.items():
            allocation = selected.throughput_result.request_allocations[request_key]
            tree.request.attr["fixed_swapping_tree"] = tree.root
            tree.request.attr["end_to_end_throughput"] = allocation.allocated_rate
    return result

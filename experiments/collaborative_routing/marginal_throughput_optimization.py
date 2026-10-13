"""PF total-throughput marginal-price optimization on fixed swapping trees."""

from dataclasses import dataclass, replace
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
    progressive_fill_end_to_end_throughput,
)


@dataclass(frozen=True)
class MarginalThroughputConfig:
    maximum_iterations: int = 15
    capacity_perturbation_fraction: float = 0.05
    minimum_capacity_perturbation: float = 1.0
    utilization_threshold: float = 0.90
    price_smoothing: float = 0.30
    price_floor_fraction: float = 0.10
    fidelity_relaxation: float = 0.25
    retained_configuration_candidates: int = 3
    objective_tolerance: float = 1e-9
    relative_improvement_tolerance: float = 0.005
    no_improvement_patience: int = 3

    def validate(self) -> None:
        if self.maximum_iterations < 1 or self.no_improvement_patience < 1:
            raise ValueError("iteration limits must be positive")
        if self.capacity_perturbation_fraction <= 0:
            raise ValueError("capacity perturbation fraction must be positive")
        if self.minimum_capacity_perturbation <= 0:
            raise ValueError("minimum capacity perturbation must be positive")
        if not 0 < self.utilization_threshold <= 1:
            raise ValueError("utilization threshold must be in (0, 1]")
        if not 0 < self.price_smoothing <= 1:
            raise ValueError("price smoothing must be in (0, 1]")
        if not 0 <= self.price_floor_fraction <= 1:
            raise ValueError("price floor fraction must be in [0, 1]")
        if not 0 < self.fidelity_relaxation <= 1:
            raise ValueError("fidelity relaxation must be in (0, 1]")
        if self.retained_configuration_candidates < 1:
            raise ValueError("at least one configuration candidate is required")


@dataclass
class MarginalThroughputIterationRecord:
    iteration: int
    quality_result: QualityAllocationResult
    configuration_result: LinkConfigurationResult
    fixed_trees: Dict[int, RequestSwappingTree]
    throughput_result: EndToEndThroughputResult
    marginal_prices: Dict[QuantumChannel, float]
    searched_channels: List[QuantumChannel]
    evaluated_candidates: int
    accepted: bool


@dataclass
class MarginalThroughputResult:
    base_stage_one_result: object
    records: List[MarginalThroughputIterationRecord]
    converged: bool
    stop_reason: str
    base_runtime_seconds: float
    refinement_runtime_seconds: float

    @property
    def refinement_iterations(self) -> int:
        return max(0, len(self.records) - 1)

    @property
    def best_record(self) -> MarginalThroughputIterationRecord:
        return max(
            self.records,
            key=lambda record: total_throughput_objective(
                record.throughput_result
            ),
        )

    @property
    def selected_record(self) -> MarginalThroughputIterationRecord:
        return self.best_record


def _jain(result: EndToEndThroughputResult) -> float:
    rates = [item.allocated_rate for item in result.request_allocations.values()]
    denominator = len(rates) * sum(rate * rate for rate in rates)
    return sum(rates) ** 2 / denominator if denominator > 0 else 0.0


def total_throughput_objective(
    result: EndToEndThroughputResult,
) -> Tuple[float, float, float, float]:
    """Total PF EDR is primary; fairness metrics break exact ties only."""
    return (
        result.total_edr,
        result.minimum_request_edr,
        _jain(result),
        result.request_acceptance_rate,
    )


def _decision(
    channel: QuantumChannel,
    selected: Optional[LinkConfigurationEvaluation],
    evaluated_count: int,
    feasible_count: int,
) -> LinkConfigurationDecision:
    return LinkConfigurationDecision(
        channel, selected, evaluated_count, feasible_count
    )


def _replace_capacity(
    configuration: LinkConfigurationResult,
    channel: QuantumChannel,
    raw_rate: float,
) -> LinkConfigurationResult:
    decisions = dict(configuration.decisions)
    old = decisions[channel]
    selected = replace(
        old.selected,
        raw_rate=raw_rate,
        effective_rate=(
            raw_rate / old.selected.average_raw_pairs
            if old.selected.average_raw_pairs > 0 else 0.0
        ),
    )
    decisions[channel] = _decision(
        channel, selected, old.evaluated_count, old.feasible_count
    )
    return LinkConfigurationResult(decisions)


def _raw_costs(trees: Mapping[int, RequestSwappingTree]):
    return {request_key: tree.raw_costs for request_key, tree in trees.items()}


def calculate_total_throughput_marginal_prices(
    quality_result: QualityAllocationResult,
    configuration_result: LinkConfigurationResult,
    fixed_trees: Mapping[int, RequestSwappingTree],
    throughput: EndToEndThroughputResult,
    previous_prices: Mapping[QuantumChannel, float],
    config: MarginalThroughputConfig,
) -> Tuple[Dict[QuantumChannel, float], List[QuantumChannel]]:
    """Estimate d(sum x_r)/dC_e by finite-difference PF evaluations."""
    eligible = []
    raw_marginals = {}
    for channel, link in throughput.link_allocations.items():
        has_unsatisfied_request = any(
            channel in item.channels and not item.fully_satisfied
            for item in throughput.request_allocations.values()
        )
        if (
            link.utilization < config.utilization_threshold
            or not has_unsatisfied_request
        ):
            raw_marginals[channel] = 0.0
            continue
        delta = max(
            config.minimum_capacity_perturbation,
            config.capacity_perturbation_fraction * link.raw_capacity,
        )
        perturbed = _replace_capacity(
            configuration_result, channel, link.raw_capacity + delta
        )
        trial = progressive_fill_end_to_end_throughput(
            quality_result,
            perturbed,
            include_swapping_failures=False,
            request_link_raw_costs=_raw_costs(fixed_trees),
            mutate_requests=False,
        )
        marginal = max(0.0, (trial.total_edr - throughput.total_edr) / delta)
        raw_marginals[channel] = marginal
        if marginal > config.objective_tolerance:
            eligible.append(channel)

    old_mean = (
        sum(previous_prices.values()) / len(previous_prices)
        if previous_prices else 1.0
    )
    positive = [raw_marginals[channel] for channel in eligible]
    positive_mean = sum(positive) / len(positive) if positive else 1.0
    floor = max(1e-9, config.price_floor_fraction * old_mean)
    prices = {}
    for channel in throughput.link_allocations:
        target = (
            old_mean * raw_marginals[channel] / positive_mean
            if raw_marginals[channel] > 0 else floor
        )
        target = max(floor, target)
        old = previous_prices.get(channel, old_mean)
        prices[channel] = (
            (1.0 - config.price_smoothing) * old
            + config.price_smoothing * target
        )
    return prices, eligible


def _fidelity_signature(quality_result):
    return {
        (id(request_plan.request), channel): fidelity
        for request_plan in quality_result.request_plans
        if request_plan.selected_plan is not None
        for channel, fidelity in request_plan.selected_plan.fidelity_requirements.items()
    }


def _active_channels(quality_result, network):
    active = {
        channel
        for request_plan in quality_result.request_plans
        if request_plan.selected_plan is not None
        for channel in request_plan.selected_plan.channels
    }
    return [channel for channel in network.qchannels if channel in active]


def _candidate_score(
    evaluation: LinkConfigurationEvaluation,
    previous_throughput: EndToEndThroughputResult,
    previous_trees: Mapping[int, RequestSwappingTree],
) -> Tuple[float, float, float]:
    """Capacity for requests that still have residual demand."""
    weighted_pairs = 0.0
    weight_sum = 0.0
    for item in evaluation.request_decisions:
        request_key = id(item.request)
        allocation = previous_throughput.request_allocations[request_key]
        residual_fraction = max(
            0.0,
            1.0 - allocation.allocated_rate / max(allocation.demand_rate, 1e-12),
        )
        if residual_fraction <= 0:
            continue
        tree = previous_trees[request_key]
        amplification = tree.amplification_factors.get(evaluation.channel, 1.0)
        weighted_pairs += (
            residual_fraction * item.expected_raw_pairs * amplification
        )
        weight_sum += residual_fraction
    average_cost = weighted_pairs / weight_sum if weight_sum > 0 else evaluation.average_raw_pairs
    return (
        evaluation.raw_rate / max(average_cost, 1e-12),
        -evaluation.total_purification_rounds,
        -evaluation.fidelity,
    )


def select_marginal_configuration_candidates(
    quality_result: QualityAllocationResult,
    previous_configuration: LinkConfigurationResult,
    previous_throughput: EndToEndThroughputResult,
    previous_trees: Mapping[int, RequestSwappingTree],
    searched_channels: Sequence[QuantumChannel],
    scenario,
    config: MarginalThroughputConfig,
) -> Tuple[LinkConfigurationResult, Dict[int, RequestSwappingTree], EndToEndThroughputResult, int]:
    """Keep other links fixed; PF-verify top points on positive-price links."""
    requirements = collect_link_requirements(quality_result)
    lookup = build_werner_purification_lookup(
        scenario.config.links.minimum_fidelity,
        scenario.config.links.maximum_fidelity,
        scenario.config.link_configuration_search.fine_step,
        scenario.config.purification.maximum_rounds,
    )
    searched = set(searched_channels)
    decisions = {}
    candidates_by_channel = {}
    evaluated = 0

    for channel, channel_requirements in requirements.items():
        old_decision = previous_configuration.decisions[channel]
        old_fidelity = old_decision.selected.fidelity
        old_point = min(lookup, key=lambda point: abs(point.fidelity - old_fidelity))
        old_evaluation = evaluate_lookup_configuration(
            channel, channel_requirements, old_point
        )
        evaluated += 1
        if channel not in searched:
            decisions[channel] = _decision(
                channel, old_evaluation if old_evaluation.feasible else None, 1,
                int(old_evaluation.feasible),
            )
            continue

        evaluations = evaluate_lookup_configurations(
            channel, channel_requirements, lookup
        )
        evaluated += len(evaluations)
        feasible = [item for item in evaluations if item.feasible]
        ranked = sorted(
            feasible,
            key=lambda item: _candidate_score(
                item, previous_throughput, previous_trees
            ),
            reverse=True,
        )
        candidates = ranked[:config.retained_configuration_candidates]
        if old_evaluation.feasible:
            candidates.append(old_evaluation)
        candidates_by_channel[channel] = list({
            item.fidelity: item for item in candidates
        }.values())
        selected = old_evaluation if old_evaluation.feasible else (
            candidates[0] if candidates else None
        )
        decisions[channel] = _decision(
            channel, selected, len(evaluations), len(feasible)
        )

    current_configuration = LinkConfigurationResult(decisions)
    current_trees, current_throughput = allocate_fixed_swapping_tree_throughput(
        quality_result, current_configuration, mutate_requests=False
    )
    for channel in searched_channels:
        trials = []
        for evaluation in candidates_by_channel.get(channel, []):
            trial_decisions = dict(current_configuration.decisions)
            old = trial_decisions[channel]
            trial_decisions[channel] = _decision(
                channel, evaluation, old.evaluated_count, old.feasible_count
            )
            trial_configuration = LinkConfigurationResult(trial_decisions)
            trial_trees, trial_throughput = allocate_fixed_swapping_tree_throughput(
                quality_result, trial_configuration, mutate_requests=False
            )
            evaluated += 1
            trials.append((
                total_throughput_objective(trial_throughput),
                trial_configuration,
                trial_trees,
                trial_throughput,
            ))
        if trials:
            _, current_configuration, current_trees, current_throughput = max(
                trials, key=lambda item: item[0]
            )
    return current_configuration, current_trees, current_throughput, evaluated


def _activate(configuration: LinkConfigurationResult) -> None:
    for channel, decision in configuration.decisions.items():
        if decision.selected is None:
            continue
        channel.fidelity = decision.selected.fidelity
        channel.raw_entanglement_rate = decision.selected.raw_rate
        channel.bandwidth = decision.selected.raw_rate
        channel.selected_configuration = decision.selected


def run_marginal_throughput_optimized_stage_one(
    scenario,
    config: MarginalThroughputConfig = MarginalThroughputConfig(),
    mutate_requests: bool = True,
) -> MarginalThroughputResult:
    """Maximize total PF throughput using finite-difference link prices."""
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
    prices, searched_channels = calculate_total_throughput_marginal_prices(
        quality,
        configuration,
        trees,
        throughput,
        {channel: state.quality_price for channel, state in quality.link_states.items()},
        config,
    )
    records = [MarginalThroughputIterationRecord(
        0, quality, configuration, trees, throughput, dict(prices),
        searched_channels, 0, True,
    )]
    active_channels = _active_channels(quality, scenario.network)
    previous_fidelities = _fidelity_signature(quality)
    no_improvement = 0
    converged = False
    stop_reason = "maximum_iterations"

    for iteration in range(1, config.maximum_iterations + 1):
        raw_quality = allocate_fixed_path_qualities(
            scenario.network,
            requests=scenario.requests,
            maximum_purification_rounds=scenario.config.purification.maximum_rounds,
            solver_config=scenario.config.quality_allocation,
            quality_prices=prices,
            active_channels=active_channels,
            mutate_requests=False,
        )
        candidate_quality = build_relaxed_quality_result(
            raw_quality, previous_fidelities, config.fidelity_relaxation
        )
        (
            candidate_configuration,
            candidate_trees,
            candidate_throughput,
            evaluated,
        ) = select_marginal_configuration_candidates(
            candidate_quality,
            configuration,
            throughput,
            trees,
            searched_channels,
            scenario,
            config,
        )
        improvement = candidate_throughput.total_edr - throughput.total_edr
        accepted = improvement >= -config.objective_tolerance
        if not accepted:
            no_improvement += 1
            records.append(MarginalThroughputIterationRecord(
                iteration, quality, configuration, trees, throughput,
                dict(prices), searched_channels, evaluated, False,
            ))
        else:
            old_total = throughput.total_edr
            quality = candidate_quality
            configuration = candidate_configuration
            trees = candidate_trees
            throughput = candidate_throughput
            previous_fidelities = _fidelity_signature(quality)
            prices, searched_channels = calculate_total_throughput_marginal_prices(
                quality, configuration, trees, throughput, prices, config
            )
            relative = (throughput.total_edr - old_total) / max(old_total, 1e-9)
            no_improvement = (
                no_improvement + 1
                if relative <= config.relative_improvement_tolerance else 0
            )
            records.append(MarginalThroughputIterationRecord(
                iteration, quality, configuration, trees, throughput,
                dict(prices), searched_channels, evaluated, True,
            ))
        if not searched_channels:
            converged = True
            stop_reason = "no_positive_marginal_price_links"
            break
        if no_improvement >= config.no_improvement_patience:
            converged = True
            stop_reason = "no_total_edr_improvement"
            break

    result = MarginalThroughputResult(
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
        _activate(selected.configuration_result)
        for request_key, tree in selected.fixed_trees.items():
            allocation = selected.throughput_result.request_allocations[request_key]
            tree.request.attr["fixed_swapping_tree"] = tree.root
            tree.request.attr["end_to_end_throughput"] = allocation.allocated_rate
    return result

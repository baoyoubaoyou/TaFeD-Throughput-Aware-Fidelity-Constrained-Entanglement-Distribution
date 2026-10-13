"""Multi-start block search for total PF throughput on fixed swapping trees."""

from dataclasses import dataclass, replace
from itertools import product
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
from experiments.collaborative_routing.marginal_throughput_optimization import (
    MarginalThroughputConfig,
    calculate_total_throughput_marginal_prices,
    total_throughput_objective,
)
from experiments.collaborative_routing.purification_lookup import (
    build_werner_purification_lookup,
)
from experiments.collaborative_routing.quality_allocation import (
    allocate_fixed_path_qualities,
    store_quality_allocation_result,
)
from experiments.collaborative_routing.quality_models import QualityAllocationResult
from experiments.collaborative_routing.spfd import run_spfd_two_stage
from experiments.collaborative_routing.stage_one import (
    build_relaxed_quality_result,
    run_stage_one,
)
from experiments.collaborative_routing.swapping_tree import (
    RequestSwappingTree,
    allocate_fixed_swapping_tree_throughput,
    optimize_swapping_trees_and_throughput,
)
from experiments.collaborative_routing.throughput_allocation import (
    EndToEndThroughputResult,
)


@dataclass(frozen=True)
class CombinatorialThroughputConfig:
    maximum_iterations: int = 10
    fidelity_relaxations: Tuple[float, ...] = (0.125, 0.25, 0.5, 1.0)
    maximum_block_links: int = 4
    candidates_per_link: int = 2
    objective_tolerance: float = 1e-9
    tree_aware_evaluation: bool = False
    exact_tree_candidates_per_relaxation: int = 2
    marginal_config: MarginalThroughputConfig = MarginalThroughputConfig()

    def validate(self) -> None:
        if self.maximum_iterations < 1 or self.maximum_block_links < 1:
            raise ValueError("iteration and block limits must be positive")
        if self.candidates_per_link < 1:
            raise ValueError("candidates per link must be positive")
        if self.exact_tree_candidates_per_relaxation < 1:
            raise ValueError("exact tree candidate count must be positive")
        if not self.fidelity_relaxations or any(
            not 0 < value <= 1 for value in self.fidelity_relaxations
        ):
            raise ValueError("fidelity relaxations must be in (0, 1]")
        self.marginal_config.validate()


@dataclass
class CombinatorialIterationRecord:
    iteration: int
    quality_result: QualityAllocationResult
    configuration_result: LinkConfigurationResult
    fixed_trees: Dict[int, RequestSwappingTree]
    throughput_result: EndToEndThroughputResult
    marginal_prices: Dict[QuantumChannel, float]
    block_channels: List[QuantumChannel]
    selected_relaxation: float
    evaluated_combinations: int
    accepted: bool
    initialization: str


@dataclass
class CombinatorialThroughputResult:
    base_stage_one_result: object
    spfd_initial_result: object
    records: List[CombinatorialIterationRecord]
    converged: bool
    stop_reason: str
    joint_initial_total_edr: float
    spfd_initial_total_edr: float
    joint_initial_runtime_seconds: float
    spfd_initial_runtime_seconds: float
    initial_runtime_seconds: float
    search_runtime_seconds: float

    @property
    def iterations(self) -> int:
        return max(0, len(self.records) - 1)

    @property
    def selected_record(self) -> CombinatorialIterationRecord:
        return max(
            self.records,
            key=lambda record: total_throughput_objective(
                record.throughput_result
            ),
        )


def _decision(channel, selected, evaluated, feasible):
    return LinkConfigurationDecision(channel, selected, evaluated, feasible)


def _active_channels(quality_result, network):
    active = {
        channel
        for request_plan in quality_result.request_plans
        if request_plan.selected_plan is not None
        for channel in request_plan.selected_plan.channels
    }
    return [channel for channel in network.qchannels if channel in active]


def _fidelities(quality_result):
    return {
        (id(request_plan.request), channel): fidelity
        for request_plan in quality_result.request_plans
        if request_plan.selected_plan is not None
        for channel, fidelity in request_plan.selected_plan.fidelity_requirements.items()
    }


def _configuration_candidate_score(
    evaluation: LinkConfigurationEvaluation,
    throughput: EndToEndThroughputResult,
    trees: Mapping[int, RequestSwappingTree],
) -> Tuple[float, float, float]:
    weighted_cost = 0.0
    weight_sum = 0.0
    for item in evaluation.request_decisions:
        key = id(item.request)
        allocation = throughput.request_allocations[key]
        residual = max(
            0.0,
            1.0 - allocation.allocated_rate / max(allocation.demand_rate, 1e-12),
        )
        amplification = trees[key].amplification_factors.get(
            evaluation.channel, 1.0
        )
        weighted_cost += residual * item.expected_raw_pairs * amplification
        weight_sum += residual
    average_cost = (
        weighted_cost / weight_sum
        if weight_sum > 0 else evaluation.average_raw_pairs
    )
    return (
        evaluation.raw_rate / max(average_cost, 1e-12),
        -evaluation.total_purification_rounds,
        -evaluation.fidelity,
    )


def evaluate_block_configuration_search(
    quality_result: QualityAllocationResult,
    previous_configuration: LinkConfigurationResult,
    previous_throughput: EndToEndThroughputResult,
    previous_trees: Mapping[int, RequestSwappingTree],
    block_channels: Sequence[QuantumChannel],
    scenario,
    config: CombinatorialThroughputConfig,
) -> Tuple[LinkConfigurationResult, Dict[int, RequestSwappingTree], EndToEndThroughputResult, int]:
    """Jointly enumerate up to K^B configurations and verify each with PF."""
    requirements = collect_link_requirements(quality_result)
    lookup = build_werner_purification_lookup(
        scenario.config.links.minimum_fidelity,
        scenario.config.links.maximum_fidelity,
        scenario.config.link_configuration_search.fine_step,
        scenario.config.purification.maximum_rounds,
    )
    block = [channel for channel in block_channels if channel in requirements]
    block_set = set(block)
    decisions = {}
    candidate_lists = []
    evaluated = 0

    for channel, channel_requirements in requirements.items():
        old = previous_configuration.decisions[channel]
        old_point = min(
            lookup,
            key=lambda point: abs(point.fidelity - old.selected.fidelity),
        )
        old_evaluation = evaluate_lookup_configuration(
            channel, channel_requirements, old_point
        )
        evaluated += 1
        if channel not in block_set:
            if old_evaluation.feasible:
                selected = old_evaluation
                feasible_count = 1
                evaluated_count = 1
            else:
                all_evaluations = evaluate_lookup_configurations(
                    channel, channel_requirements, lookup
                )
                evaluated += len(all_evaluations)
                feasible = [item for item in all_evaluations if item.feasible]
                selected = max(
                    feasible,
                    key=lambda item: item.effective_rate,
                    default=None,
                )
                feasible_count = len(feasible)
                evaluated_count = len(all_evaluations)
            decisions[channel] = _decision(
                channel, selected, evaluated_count, feasible_count
            )
            continue

        all_evaluations = evaluate_lookup_configurations(
            channel, channel_requirements, lookup
        )
        evaluated += len(all_evaluations)
        feasible = [item for item in all_evaluations if item.feasible]
        ranked = sorted(
            feasible,
            key=lambda item: _configuration_candidate_score(
                item, previous_throughput, previous_trees
            ),
            reverse=True,
        )
        candidates = ranked[:config.candidates_per_link]
        if old_evaluation.feasible:
            candidates.append(old_evaluation)
        unique = list({item.fidelity: item for item in candidates}.values())
        # Keep the search bound exact: current point competes for the K slots.
        unique = sorted(
            unique,
            key=lambda item: _configuration_candidate_score(
                item, previous_throughput, previous_trees
            ),
            reverse=True,
        )[:config.candidates_per_link]
        candidate_lists.append((channel, unique, len(all_evaluations), len(feasible)))

    proxy_candidates = []
    combinations = product(*(items for _, items, _, _ in candidate_lists))
    for selected_items in combinations:
        trial_decisions = dict(decisions)
        for (channel, _, evaluated_count, feasible_count), selected in zip(
            candidate_lists, selected_items
        ):
            trial_decisions[channel] = _decision(
                channel, selected, evaluated_count, feasible_count
            )
        trial_configuration = LinkConfigurationResult(trial_decisions)
        trial_trees, trial_throughput = allocate_fixed_swapping_tree_throughput(
            quality_result, trial_configuration, mutate_requests=False
        )
        evaluated += 1
        candidate = (
            total_throughput_objective(trial_throughput),
            trial_configuration,
            trial_trees,
            trial_throughput,
        )
        proxy_candidates.append(candidate)

    if not proxy_candidates:
        trial_configuration = LinkConfigurationResult(decisions)
        trial_trees, trial_throughput = allocate_fixed_swapping_tree_throughput(
            quality_result, trial_configuration, mutate_requests=False
        )
        proxy_candidates.append((
            total_throughput_objective(trial_throughput),
            trial_configuration,
            trial_trees,
            trial_throughput,
        ))

    if config.tree_aware_evaluation:
        exact_candidates = []
        retained = sorted(
            proxy_candidates,
            key=lambda item: item[0],
            reverse=True,
        )[:config.exact_tree_candidates_per_relaxation]
        for _, trial_configuration, _, _ in retained:
            optimized = optimize_swapping_trees_and_throughput(
                quality_result,
                trial_configuration,
                mutate_requests=False,
            )
            selected = optimized.selected_record
            evaluated += 1
            exact = (
                total_throughput_objective(selected.throughput_result),
                trial_configuration,
                selected.trees,
                selected.throughput_result,
            )
            exact_candidates.append(exact)
        best = max(exact_candidates, key=lambda item: item[0])
    else:
        best = max(proxy_candidates, key=lambda item: item[0])
    return best[1], best[2], best[3], evaluated


def _replace_link_capacity(configuration, channel, raw_rate):
    decisions = dict(configuration.decisions)
    old = decisions[channel]
    selected = replace(
        old.selected,
        raw_rate=raw_rate,
        effective_rate=raw_rate / max(old.selected.average_raw_pairs, 1e-12),
    )
    decisions[channel] = _decision(
        channel, selected, old.evaluated_count, old.feasible_count
    )
    return LinkConfigurationResult(decisions)


def calculate_tree_aware_marginal_prices(
    quality_result,
    configuration_result,
    throughput,
    previous_prices,
    config,
):
    """Finite-difference prices after reoptimizing swapping trees and PF."""
    raw_marginals = {}
    positive_channels = []
    for channel, link in throughput.link_allocations.items():
        unsatisfied = any(
            channel in item.channels and not item.fully_satisfied
            for item in throughput.request_allocations.values()
        )
        if (
            link.utilization < config.utilization_threshold
            or not unsatisfied
        ):
            raw_marginals[channel] = 0.0
            continue
        delta = max(
            config.minimum_capacity_perturbation,
            config.capacity_perturbation_fraction * link.raw_capacity,
        )
        perturbed = _replace_link_capacity(
            configuration_result, channel, link.raw_capacity + delta
        )
        optimized = optimize_swapping_trees_and_throughput(
            quality_result,
            perturbed,
            mutate_requests=False,
        )
        trial = optimized.selected_record.throughput_result
        marginal = max(0.0, (trial.total_edr - throughput.total_edr) / delta)
        raw_marginals[channel] = marginal
        if marginal > config.objective_tolerance:
            positive_channels.append(channel)

    mean_old = (
        sum(previous_prices.values()) / len(previous_prices)
        if previous_prices else 1.0
    )
    positives = [raw_marginals[channel] for channel in positive_channels]
    mean_positive = sum(positives) / len(positives) if positives else 1.0
    floor = max(1e-9, config.price_floor_fraction * mean_old)
    prices = {}
    for channel in throughput.link_allocations:
        target = (
            mean_old * raw_marginals[channel] / mean_positive
            if raw_marginals[channel] > 0 else floor
        )
        old = previous_prices.get(channel, mean_old)
        prices[channel] = (
            (1.0 - config.price_smoothing) * old
            + config.price_smoothing * max(floor, target)
        )
    return prices, positive_channels


def _activate(configuration):
    for channel, decision in configuration.decisions.items():
        if decision.selected is None:
            continue
        channel.fidelity = decision.selected.fidelity
        channel.raw_entanglement_rate = decision.selected.raw_rate
        channel.bandwidth = decision.selected.raw_rate
        channel.selected_configuration = decision.selected


def run_combinatorial_throughput_optimized_stage_one(
    scenario,
    config: CombinatorialThroughputConfig = CombinatorialThroughputConfig(),
    mutate_requests: bool = True,
) -> CombinatorialThroughputResult:
    """Use Joint/SPFD multi-start, multi-step fidelity, and block search."""
    config.validate()
    initial_started = perf_counter()
    joint_started = perf_counter()
    joint = run_stage_one(scenario)
    joint_record = joint.selected_record
    joint_trees, joint_throughput = allocate_fixed_swapping_tree_throughput(
        joint_record.quality_result,
        joint_record.configuration_result,
        mutate_requests=False,
    )
    if config.tree_aware_evaluation:
        joint_optimized = optimize_swapping_trees_and_throughput(
            joint_record.quality_result,
            joint_record.configuration_result,
            mutate_requests=False,
        ).selected_record
        joint_trees = joint_optimized.trees
        joint_throughput = joint_optimized.throughput_result
    joint_runtime = perf_counter() - joint_started
    spfd_started = perf_counter()
    spfd = run_spfd_two_stage(
        scenario,
        path_quality_result=joint_record.quality_result,
        mutate_requests=False,
    )
    spfd_trees, spfd_throughput = allocate_fixed_swapping_tree_throughput(
        spfd.quality_result, spfd.configuration_result, mutate_requests=False
    )
    if config.tree_aware_evaluation:
        spfd_optimized = optimize_swapping_trees_and_throughput(
            spfd.quality_result,
            spfd.configuration_result,
            mutate_requests=False,
        ).selected_record
        spfd_trees = spfd_optimized.trees
        spfd_throughput = spfd_optimized.throughput_result
    spfd_runtime = perf_counter() - spfd_started
    if total_throughput_objective(spfd_throughput) > total_throughput_objective(
        joint_throughput
    ):
        initialization = "SPFD"
        quality = spfd.quality_result
        configuration = spfd.configuration_result
        trees = spfd_trees
        throughput = spfd_throughput
    else:
        initialization = "Joint_v1"
        quality = joint_record.quality_result
        configuration = joint_record.configuration_result
        trees = joint_trees
        throughput = joint_throughput
    initial_runtime = perf_counter() - initial_started
    search_started = perf_counter()
    active_channels = _active_channels(quality, scenario.network)
    previous_fidelities = _fidelities(quality)
    initial_prices = {
        channel: state.quality_price
        for channel, state in quality.link_states.items()
    }
    if config.tree_aware_evaluation:
        prices, positive_channels = calculate_tree_aware_marginal_prices(
            quality, configuration, throughput, initial_prices,
            config.marginal_config,
        )
    else:
        prices, positive_channels = calculate_total_throughput_marginal_prices(
            quality, configuration, trees, throughput, initial_prices,
            config.marginal_config,
        )
    block_channels = sorted(
        positive_channels, key=lambda channel: prices[channel], reverse=True
    )[:config.maximum_block_links]
    records = [CombinatorialIterationRecord(
        0, quality, configuration, trees, throughput, dict(prices),
        block_channels, 0.0, 0, True, initialization,
    )]
    converged = False
    stop_reason = "maximum_iterations"

    for iteration in range(1, config.maximum_iterations + 1):
        if not block_channels:
            converged = True
            stop_reason = "no_positive_marginal_price_links"
            break
        raw_quality = allocate_fixed_path_qualities(
            scenario.network,
            requests=scenario.requests,
            maximum_purification_rounds=scenario.config.purification.maximum_rounds,
            solver_config=scenario.config.quality_allocation,
            quality_prices=prices,
            active_channels=active_channels,
            mutate_requests=False,
        )
        candidates = []
        total_evaluated = 0
        for relaxation in config.fidelity_relaxations:
            candidate_quality = build_relaxed_quality_result(
                raw_quality, previous_fidelities, relaxation
            )
            (
                candidate_configuration,
                candidate_trees,
                candidate_throughput,
                evaluated,
            ) = evaluate_block_configuration_search(
                candidate_quality,
                configuration,
                throughput,
                trees,
                block_channels,
                scenario,
                config,
            )
            total_evaluated += evaluated
            candidates.append((
                total_throughput_objective(candidate_throughput),
                relaxation,
                candidate_quality,
                candidate_configuration,
                candidate_trees,
                candidate_throughput,
            ))
        (
            _, relaxation, candidate_quality, candidate_configuration,
            candidate_trees, candidate_throughput,
        ) = max(candidates, key=lambda item: item[0])
        improvement = candidate_throughput.total_edr - throughput.total_edr
        if improvement <= config.objective_tolerance:
            records.append(CombinatorialIterationRecord(
                iteration, quality, configuration, trees, throughput,
                dict(prices), block_channels, relaxation, total_evaluated,
                False, initialization,
            ))
            converged = True
            stop_reason = "no_improving_block_configuration"
            break

        quality = candidate_quality
        configuration = candidate_configuration
        trees = candidate_trees
        throughput = candidate_throughput
        previous_fidelities = _fidelities(quality)
        if config.tree_aware_evaluation:
            prices, positive_channels = calculate_tree_aware_marginal_prices(
                quality, configuration, throughput, prices,
                config.marginal_config,
            )
        else:
            prices, positive_channels = calculate_total_throughput_marginal_prices(
                quality, configuration, trees, throughput, prices,
                config.marginal_config,
            )
        block_channels = sorted(
            positive_channels, key=lambda channel: prices[channel], reverse=True
        )[:config.maximum_block_links]
        records.append(CombinatorialIterationRecord(
            iteration, quality, configuration, trees, throughput,
            dict(prices), block_channels, relaxation, total_evaluated,
            True, initialization,
        ))

    result = CombinatorialThroughputResult(
        joint,
        spfd,
        records,
        converged,
        stop_reason,
        joint_throughput.total_edr,
        spfd_throughput.total_edr,
        joint_runtime,
        spfd_runtime,
        initial_runtime,
        perf_counter() - search_started,
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


def run_tree_aware_combinatorial_throughput(
    scenario,
    config: CombinatorialThroughputConfig = CombinatorialThroughputConfig(),
    mutate_requests: bool = True,
) -> CombinatorialThroughputResult:
    """Run block search whose prices and accepted objective include optimal trees."""
    return run_combinatorial_throughput_optimized_stage_one(
        scenario,
        config=replace(config, tree_aware_evaluation=True),
        mutate_requests=mutate_requests,
    )

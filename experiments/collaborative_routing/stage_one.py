"""Joint iteration of stage I-A quality allocation and stage I-B configuration."""

from dataclasses import replace
from typing import Dict, Mapping, Optional, Tuple

from qns.entity.qchannel.qchannel import QuantumChannel

from experiments.collaborative_routing.configuration_models import (
    LinkConfigurationResult,
    StageOneIterationRecord,
    StageOneResult,
)
from experiments.collaborative_routing.link_configuration import (
    raw_entanglement_rate,
    select_all_link_configurations,
)
from experiments.collaborative_routing.quality_allocation import (
    allocate_all_request_qualities,
    allocate_fixed_path_qualities,
    calculate_end_to_end_fidelity,
    store_quality_allocation_result,
)
from experiments.collaborative_routing.quality_models import QualityAllocationResult


def update_quality_prices(
    old_prices: Mapping[QuantumChannel, float],
    configuration_result: LinkConfigurationResult,
    scenario,
) -> Dict[QuantumChannel, float]:
    """Apply the normalized effective-rate price feedback equation."""
    iteration_config = scenario.config.stage_one_iteration
    lambda_0 = scenario.config.quality_allocation.lambda_0
    updated = dict(old_prices)
    for channel, decision in configuration_result.decisions.items():
        old_price = float(old_prices[channel])
        if decision.selected is None:
            updated[channel] = old_price * iteration_config.infeasible_price_multiplier
            continue
        reference_rate = raw_entanglement_rate(
            channel,
            scenario.config.links.minimum_fidelity,
        )
        normalized_rate = max(
            decision.selected.effective_rate / reference_rate,
            iteration_config.normalized_rate_floor,
        )
        target_price = lambda_0 + 1.0 / (
            normalized_rate + iteration_config.normalized_rate_regularization
        )
        beta = iteration_config.price_smoothing
        updated[channel] = (1.0 - beta) * old_price + beta * target_price
    return updated


def _configuration_signature(
    result: LinkConfigurationResult,
) -> Dict[QuantumChannel, Optional[float]]:
    return {
        channel: None if decision.selected is None else decision.selected.fidelity
        for channel, decision in result.decisions.items()
    }


def _fidelity_signature(quality_result) -> Dict[Tuple[int, QuantumChannel], float]:
    values = {}
    for request_plan in quality_result.request_plans:
        selected = request_plan.selected_plan
        if selected is None:
            continue
        for channel, fidelity in selected.fidelity_requirements.items():
            values[(id(request_plan.request), channel)] = fidelity
    return values


def _maximum_fidelity_change(current, previous) -> Optional[float]:
    if previous is None:
        return None
    shared = set(current).intersection(previous)
    if not shared:
        return None
    return max(abs(current[key] - previous[key]) for key in shared)


def build_relaxed_quality_result(
    quality_result,
    previous_fidelities: Mapping[Tuple[int, QuantumChannel], float],
    relaxation: float,
) -> QualityAllocationResult:
    """Return a relaxed copy of a stage-I-A allocation without changing requests."""
    if not 0 < relaxation <= 1:
        raise ValueError("fidelity relaxation must be in (0, 1]")
    relaxed_request_plans = []
    for request_plan in quality_result.request_plans:
        selected = request_plan.selected_plan
        if selected is None:
            relaxed_request_plans.append(request_plan)
            continue
        request_key = id(request_plan.request)
        damped = {}
        for channel, new_fidelity in selected.fidelity_requirements.items():
            previous = previous_fidelities.get((request_key, channel), new_fidelity)
            damped[channel] = (
                (1.0 - relaxation) * previous + relaxation * new_fidelity
            )
        quality_cost = sum(
            quality_result.link_states[channel].quality_price * fidelity
            for channel, fidelity in damped.items()
        )
        incremental_quality_cost = sum(
            quality_result.link_states[channel].quality_price
            * (fidelity - quality_result.link_states[channel].lower_fidelity)
            for channel, fidelity in damped.items()
        )
        achieved_fidelity = calculate_end_to_end_fidelity(
            selected.path,
            selected.channels,
            damped,
        )
        relaxed_plan = replace(
            selected,
            fidelity_requirements=damped,
            quality_cost=quality_cost,
            incremental_quality_cost=incremental_quality_cost,
            achieved_fidelity=achieved_fidelity,
            status="allocated_relaxed",
            water_level=None,
        )
        relaxed_request_plans.append(replace(
            request_plan,
            candidate_plans=[relaxed_plan],
            selected_candidate_index=relaxed_plan.candidate_index,
        ))
    return QualityAllocationResult(
        link_states=quality_result.link_states,
        request_plans=relaxed_request_plans,
    )


def damp_quality_requirements(
    quality_result,
    previous_fidelities: Mapping[Tuple[int, QuantumChannel], float],
    relaxation: float,
) -> None:
    """Compatibility interface for the preserved fixed-damping baseline."""
    relaxed = build_relaxed_quality_result(
        quality_result,
        previous_fidelities,
        relaxation,
    )
    quality_result.request_plans = relaxed.request_plans
    store_quality_allocation_result(quality_result)


def calculate_request_capacity_proxy(
    configuration_result: LinkConfigurationResult,
) -> Tuple[float, float]:
    """Return min and total demand-weighted request bottleneck capacities."""
    capacities: Dict[int, float] = {}
    for decision in configuration_result.decisions.values():
        selected = decision.selected
        if selected is None:
            return 0.0, 0.0
        for request_decision in selected.request_decisions:
            capacity = (
                selected.raw_rate
                * request_decision.demand_weight
                / request_decision.expected_raw_pairs
            )
            request_key = id(request_decision.request)
            capacities[request_key] = min(
                capacities.get(request_key, float("inf")),
                capacity,
            )
    if not capacities:
        return 0.0, 0.0
    return min(capacities.values()), sum(capacities.values())


def _activate_configurations(configuration_result: LinkConfigurationResult) -> None:
    """Restore channel state after evaluating multiple adaptive candidates."""
    for channel, decision in configuration_result.decisions.items():
        selected = decision.selected
        if selected is None:
            continue
        channel.active_profile_index = None
        channel.fidelity = selected.fidelity
        channel.raw_entanglement_rate = selected.raw_rate
        channel.bandwidth = selected.raw_rate
        channel.selected_configuration = selected


def _select_relaxed_candidate(
    raw_quality_result: QualityAllocationResult,
    previous_fidelities: Mapping[Tuple[int, QuantumChannel], float],
    scenario,
    previous_minimum_capacity: Optional[float] = None,
    previous_total_capacity: Optional[float] = None,
) -> Tuple[QualityAllocationResult, LinkConfigurationResult, float, float, float, int]:
    """Evaluate the configured relaxation candidates and keep the fairest one."""
    iteration_config = scenario.config.stage_one_iteration
    relaxations = (
        (iteration_config.fidelity_relaxation,)
        if iteration_config.fidelity_update_mode == "fixed"
        else iteration_config.adaptive_fidelity_relaxations
    )
    candidates = []
    for relaxation in relaxations:
        quality_result = build_relaxed_quality_result(
            raw_quality_result,
            previous_fidelities,
            relaxation,
        )
        configuration_result = select_all_link_configurations(
            quality_result,
            scenario.config.links,
            scenario.config.link_configuration_search,
            scenario.config.purification.maximum_rounds,
        )
        minimum_capacity, total_capacity = calculate_request_capacity_proxy(
            configuration_result
        )
        key = (
            configuration_result.infeasible_links == 0,
            minimum_capacity,
            total_capacity,
            configuration_result.total_effective_rate,
            -configuration_result.average_purification_rounds,
            relaxation,
        )
        candidates.append((key, quality_result, configuration_result, relaxation))
        if iteration_config.adaptive_early_accept:
            tolerance = iteration_config.adaptive_acceptance_tolerance
            minimum_acceptable = (
                0.0
                if previous_minimum_capacity is None
                else previous_minimum_capacity * (1.0 - tolerance)
            )
            total_acceptable = (
                0.0
                if previous_total_capacity is None
                else previous_total_capacity * (1.0 - tolerance)
            )
            if (
                configuration_result.infeasible_links == 0
                and minimum_capacity >= minimum_acceptable
                and total_capacity >= total_acceptable
            ):
                break

    _, quality_result, configuration_result, relaxation = max(
        candidates,
        key=lambda candidate: candidate[0],
    )
    _activate_configurations(configuration_result)
    minimum_capacity, total_capacity = calculate_request_capacity_proxy(
        configuration_result
    )
    return (
        quality_result,
        configuration_result,
        relaxation,
        minimum_capacity,
        total_capacity,
        len(candidates),
    )


def _active_channels(quality_result, network) -> list[QuantumChannel]:
    active = {
        channel
        for request_plan in quality_result.request_plans
        if request_plan.selected_plan is not None
        for channel in request_plan.selected_plan.channels
    }
    return [channel for channel in network.qchannels if channel in active]


def _store_purification_results(configuration_result: LinkConfigurationResult) -> None:
    per_request: Dict[int, Dict[str, Dict[str, float]]] = {}
    request_objects = {}
    for channel, decision in configuration_result.decisions.items():
        if decision.selected is None:
            continue
        for item in decision.selected.request_decisions:
            request_key = id(item.request)
            request_objects[request_key] = item.request
            per_request.setdefault(request_key, {})[channel.name] = {
                "base_fidelity": decision.selected.fidelity,
                "raw_rate": decision.selected.raw_rate,
                "effective_link_rate": decision.selected.effective_rate,
                "purification_rounds": item.rounds,
                "output_fidelity": item.output_fidelity,
                "expected_raw_pairs": item.expected_raw_pairs,
                "memory_slots_per_endpoint": item.memory_slots_per_endpoint,
            }
    for request_key, values in per_request.items():
        request_objects[request_key].attr["purification_decisions"] = values


def run_stage_one(scenario) -> StageOneResult:
    """Run the bounded I-A/I-B feedback loop with paths fixed after round one."""
    iteration_config = scenario.config.stage_one_iteration
    records = []
    quality_prices = None
    previous_objective = None
    previous_configuration = None
    previous_fidelities = None
    previous_minimum_capacity = None
    previous_total_capacity = None
    active_channels = None
    converged = False
    stop_reason = "maximum_iterations"

    for iteration in range(1, iteration_config.maximum_iterations + 1):
        if iteration == 1:
            quality_result = allocate_all_request_qualities(
                scenario.network,
                requests=scenario.requests,
                maximum_purification_rounds=scenario.config.purification.maximum_rounds,
                solver_config=scenario.config.quality_allocation,
                mutate_requests=True,
            )
            configuration_result = select_all_link_configurations(
                quality_result,
                scenario.config.links,
                scenario.config.link_configuration_search,
                scenario.config.purification.maximum_rounds,
            )
            selected_relaxation = 1.0
            evaluated_relaxation_count = 1
            minimum_request_capacity, total_request_capacity = (
                calculate_request_capacity_proxy(configuration_result)
            )
            active_channels = _active_channels(quality_result, scenario.network)
        else:
            raw_quality_result = allocate_fixed_path_qualities(
                scenario.network,
                requests=scenario.requests,
                maximum_purification_rounds=scenario.config.purification.maximum_rounds,
                solver_config=scenario.config.quality_allocation,
                quality_prices=quality_prices,
                active_channels=(
                    active_channels if iteration_config.active_links_only else None
                ),
                mutate_requests=False,
            )
            (
                quality_result,
                configuration_result,
                selected_relaxation,
                minimum_request_capacity,
                total_request_capacity,
                evaluated_relaxation_count,
            ) = _select_relaxed_candidate(
                raw_quality_result,
                previous_fidelities,
                scenario,
                previous_minimum_capacity,
                previous_total_capacity,
            )
            store_quality_allocation_result(quality_result)

        quality_prices_before_feedback = {
            channel: state.quality_price
            for channel, state in quality_result.link_states.items()
        }
        objective = configuration_result.total_effective_rate
        relative_change = None
        if previous_objective is not None:
            relative_change = abs(objective - previous_objective) / max(
                abs(previous_objective),
                iteration_config.normalized_rate_floor,
            )
        configuration = _configuration_signature(configuration_result)
        configuration_unchanged = (
            previous_configuration is not None and configuration == previous_configuration
        )
        fidelities = _fidelity_signature(quality_result)
        maximum_fidelity_change = _maximum_fidelity_change(fidelities, previous_fidelities)
        records.append(StageOneIterationRecord(
            iteration=iteration,
            quality_result=quality_result,
            configuration_result=configuration_result,
            objective=objective,
            relative_change=relative_change,
            configuration_unchanged=configuration_unchanged,
            maximum_fidelity_change=maximum_fidelity_change,
            selected_relaxation=selected_relaxation,
            minimum_request_capacity=minimum_request_capacity,
            total_request_capacity=total_request_capacity,
            evaluated_relaxation_count=evaluated_relaxation_count,
        ))
        _store_purification_results(configuration_result)
        quality_prices = update_quality_prices(
            quality_prices_before_feedback,
            configuration_result,
            scenario,
        )

        all_links_feasible = configuration_result.infeasible_links == 0
        small_improvement = (
            relative_change is not None
            and relative_change <= iteration_config.relative_improvement_tolerance
        )
        stable_configuration = (
            iteration_config.stop_when_configuration_unchanged
            and configuration_unchanged
        )
        if all_links_feasible and small_improvement and stable_configuration:
            converged = True
            stop_reason = "relative_change_and_configuration_unchanged"
            break

        previous_objective = objective
        previous_configuration = configuration
        previous_fidelities = fidelities
        previous_minimum_capacity = minimum_request_capacity
        previous_total_capacity = total_request_capacity

    result = StageOneResult(records, quality_prices or {}, converged, stop_reason)
    selected = result.selected_record
    _activate_configurations(selected.configuration_result)
    store_quality_allocation_result(selected.quality_result)
    _store_purification_results(selected.configuration_result)
    return result

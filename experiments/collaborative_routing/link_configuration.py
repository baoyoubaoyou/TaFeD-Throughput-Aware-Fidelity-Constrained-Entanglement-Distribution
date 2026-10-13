"""Stage I-B: choose one shared base-fidelity configuration per active link."""

from typing import Dict, Iterable, List, Mapping, Sequence, Tuple

from qns.entity.qchannel.qchannel import QuantumChannel
from qns.network.requests import Request

from experiments.collaborative_routing.config import (
    LinkConfig,
    LinkConfigurationSearchConfig,
)
from experiments.collaborative_routing.configuration_models import (
    LinkConfigurationDecision,
    LinkConfigurationEvaluation,
    LinkConfigurationResult,
    RequestPurificationDecision,
)
from experiments.collaborative_routing.purification import fidelity_after_rounds, minimum_plan
from experiments.collaborative_routing.purification_lookup import (
    PurificationLookupPoint,
    build_werner_purification_lookup,
    find_minimum_lookup_plan,
)
from experiments.collaborative_routing.quality_models import QualityAllocationResult


def raw_entanglement_rate(channel: QuantumChannel, fidelity: float) -> float:
    """Evaluate the configured heterogeneous rate curve R_e(F)."""
    generation_capacity = float(getattr(channel, "generation_capacity"))
    return 0.75 * generation_capacity * (1.0 - fidelity)


def memory_limited_raw_rate(channel: QuantumChannel, generated_rate: float) -> float:
    """Apply the node-memory share assigned to this physical link."""
    memory_rate = float(getattr(channel, "memory_bandwidth", float("inf")))
    return min(float(generated_rate), memory_rate)


def purification_memory_slots(rounds: int) -> int:
    """Peak endpoint memory for one nested purification operation."""
    if rounds < 0:
        raise ValueError("purification rounds cannot be negative")
    return 1 << rounds


def _endpoint_memory(channel: QuantumChannel) -> int:
    capacities = [
        sum(int(memory.capacity) for memory in node.memories)
        for node in channel.node_list
    ]
    return min(capacities) if capacities else 0


def collect_link_requirements(
    quality_result: QualityAllocationResult,
) -> Dict[QuantumChannel, List[Tuple[Request, float]]]:
    """Group selected request-level fidelity thresholds by physical link."""
    grouped: Dict[QuantumChannel, List[Tuple[Request, float]]] = {}
    for request_plan in quality_result.request_plans:
        selected = request_plan.selected_plan
        if selected is None:
            continue
        for channel, required_fidelity in selected.fidelity_requirements.items():
            grouped.setdefault(channel, []).append(
                (request_plan.request, float(required_fidelity))
            )
    return grouped


def evaluate_link_configuration(
    channel: QuantumChannel,
    requirements: Sequence[Tuple[Request, float]],
    fidelity: float,
    maximum_purification_rounds: int,
) -> LinkConfigurationEvaluation:
    """Evaluate quality, memory, expected-pair cost, and effective rate."""
    raw_rate = raw_entanglement_rate(channel, fidelity)
    total_demand = sum(float(request.attr["demand_intensity"]) for request, _ in requirements)
    if total_demand <= 0:
        return LinkConfigurationEvaluation(
            channel, fidelity, False, raw_rate, failure_reason="non-positive total demand"
        )

    memory_capacity = _endpoint_memory(channel)
    decisions = []
    weighted_raw_pairs = 0.0
    for request, required_fidelity in requirements:
        plan = minimum_plan(fidelity, required_fidelity, maximum_purification_rounds)
        if plan is None:
            return LinkConfigurationEvaluation(
                channel,
                fidelity,
                False,
                raw_rate,
                failure_reason="quality target exceeds the maximum purification depth",
            )
        memory_slots = purification_memory_slots(plan.rounds)
        if memory_slots > memory_capacity:
            return LinkConfigurationEvaluation(
                channel,
                fidelity,
                False,
                raw_rate,
                failure_reason=(
                    f"purification needs {memory_slots} memory slots but only "
                    f"{memory_capacity} are available per endpoint"
                ),
            )
        demand_weight = float(request.attr["demand_intensity"]) / total_demand
        weighted_raw_pairs += demand_weight * plan.expected_raw_pairs
        decisions.append(RequestPurificationDecision(
            request=request,
            required_fidelity=required_fidelity,
            demand_weight=demand_weight,
            rounds=plan.rounds,
            output_fidelity=plan.output_fidelity,
            expected_raw_pairs=plan.expected_raw_pairs,
            memory_slots_per_endpoint=memory_slots,
        ))

    return LinkConfigurationEvaluation(
        channel=channel,
        fidelity=fidelity,
        feasible=True,
        raw_rate=raw_rate,
        effective_rate=memory_limited_raw_rate(channel, raw_rate) / weighted_raw_pairs,
        average_raw_pairs=weighted_raw_pairs,
        total_purification_rounds=sum(item.rounds for item in decisions),
        request_decisions=decisions,
    )


def evaluate_lookup_configuration(
    channel: QuantumChannel,
    requirements: Sequence[Tuple[Request, float]],
    point: PurificationLookupPoint,
) -> LinkConfigurationEvaluation:
    """Evaluate a configuration using a scenario-independent Werner table."""
    fidelity = point.fidelity
    raw_rate = raw_entanglement_rate(channel, fidelity)
    total_demand = sum(float(request.attr["demand_intensity"]) for request, _ in requirements)
    if total_demand <= 0:
        return LinkConfigurationEvaluation(
            channel, fidelity, False, raw_rate, failure_reason="non-positive total demand"
        )

    memory_capacity = _endpoint_memory(channel)
    decisions = []
    weighted_raw_pairs = 0.0
    for request, required_fidelity in requirements:
        plan = find_minimum_lookup_plan(point, required_fidelity)
        if plan is None:
            return LinkConfigurationEvaluation(
                channel,
                fidelity,
                False,
                raw_rate,
                failure_reason="quality target exceeds the maximum purification depth",
            )
        if plan.memory_slots_per_endpoint > memory_capacity:
            return LinkConfigurationEvaluation(
                channel,
                fidelity,
                False,
                raw_rate,
                failure_reason=(
                    f"purification needs {plan.memory_slots_per_endpoint} memory slots "
                    f"but only {memory_capacity} are available per endpoint"
                ),
            )
        demand_weight = float(request.attr["demand_intensity"]) / total_demand
        weighted_raw_pairs += demand_weight * plan.expected_raw_pairs
        decisions.append(RequestPurificationDecision(
            request=request,
            required_fidelity=required_fidelity,
            demand_weight=demand_weight,
            rounds=plan.rounds,
            output_fidelity=plan.output_fidelity,
            expected_raw_pairs=plan.expected_raw_pairs,
            memory_slots_per_endpoint=plan.memory_slots_per_endpoint,
        ))

    return LinkConfigurationEvaluation(
        channel=channel,
        fidelity=fidelity,
        feasible=True,
        raw_rate=raw_rate,
        effective_rate=memory_limited_raw_rate(channel, raw_rate) / weighted_raw_pairs,
        average_raw_pairs=weighted_raw_pairs,
        total_purification_rounds=sum(item.rounds for item in decisions),
        request_decisions=decisions,
    )


def evaluate_lookup_configurations(
    channel: QuantumChannel,
    requirements: Sequence[Tuple[Request, float]],
    points: Sequence[PurificationLookupPoint],
) -> List[LinkConfigurationEvaluation]:
    """Evaluate one 0.001 grid while reusing all link-level invariants."""
    demands = [
        float(request.attr["demand_intensity"])
        for request, _ in requirements
    ]
    total_demand = sum(demands)
    memory_capacity = _endpoint_memory(channel)
    rate_scale = 0.75 * float(getattr(channel, "generation_capacity"))
    prepared = [
        (request, float(required_fidelity), demand / total_demand)
        for (request, required_fidelity), demand in zip(requirements, demands)
    ] if total_demand > 0 else []
    evaluations = []
    for point in points:
        fidelity = point.fidelity
        raw_rate = rate_scale * (1.0 - fidelity)
        if total_demand <= 0:
            evaluations.append(LinkConfigurationEvaluation(
                channel, fidelity, False, raw_rate,
                failure_reason="non-positive total demand",
            ))
            continue
        decisions = []
        weighted_raw_pairs = 0.0
        failure_reason = None
        for request, required_fidelity, demand_weight in prepared:
            plan = find_minimum_lookup_plan(point, required_fidelity)
            if plan is None:
                failure_reason = (
                    "quality target exceeds the maximum purification depth"
                )
                break
            if plan.memory_slots_per_endpoint > memory_capacity:
                failure_reason = (
                    f"purification needs {plan.memory_slots_per_endpoint} memory slots "
                    f"but only {memory_capacity} are available per endpoint"
                )
                break
            weighted_raw_pairs += demand_weight * plan.expected_raw_pairs
            decisions.append(RequestPurificationDecision(
                request=request,
                required_fidelity=required_fidelity,
                demand_weight=demand_weight,
                rounds=plan.rounds,
                output_fidelity=plan.output_fidelity,
                expected_raw_pairs=plan.expected_raw_pairs,
                memory_slots_per_endpoint=plan.memory_slots_per_endpoint,
            ))
        if failure_reason is not None:
            evaluations.append(LinkConfigurationEvaluation(
                channel, fidelity, False, raw_rate,
                failure_reason=failure_reason,
            ))
            continue
        evaluations.append(LinkConfigurationEvaluation(
            channel=channel,
            fidelity=fidelity,
            feasible=True,
            raw_rate=raw_rate,
            effective_rate=memory_limited_raw_rate(channel, raw_rate) / weighted_raw_pairs,
            average_raw_pairs=weighted_raw_pairs,
            total_purification_rounds=sum(item.rounds for item in decisions),
            request_decisions=decisions,
        ))
    return evaluations


def search_link_configuration_with_lookup(
    channel: QuantumChannel,
    requirements: Sequence[Tuple[Request, float]],
    link_config: LinkConfig,
    search_config: LinkConfigurationSearchConfig,
    maximum_purification_rounds: int,
) -> LinkConfigurationDecision:
    """Exhaust the cached fidelity grid and return its exact discrete optimum."""
    lookup = build_werner_purification_lookup(
        link_config.minimum_fidelity,
        link_config.maximum_fidelity,
        search_config.fine_step,
        maximum_purification_rounds,
    )
    evaluations = evaluate_lookup_configurations(channel, requirements, lookup)
    selected = _best_evaluation(evaluations)
    if selected is not None:
        channel.active_profile_index = None
        channel.fidelity = selected.fidelity
        channel.raw_entanglement_rate = selected.raw_rate
        channel.bandwidth = selected.raw_rate
        channel.selected_configuration = selected
    return LinkConfigurationDecision(
        channel=channel,
        selected=selected,
        evaluated_count=len(evaluations),
        feasible_count=sum(evaluation.feasible for evaluation in evaluations),
    )


def _grid(start: float, stop: float, step: float) -> List[float]:
    count = int(round((stop - start) / step))
    values = [start + index * step for index in range(count + 1)]
    if values[-1] < stop - 1e-12:
        values.append(stop)
    return [min(stop, max(start, value)) for value in values]


def _quantize(value: float, step: float, lower: float, upper: float) -> float:
    quantized = round((value - lower) / step) * step + lower
    return round(min(upper, max(lower, quantized)), 12)


def _purification_threshold(
    required_fidelity: float,
    rounds: int,
    lower: float,
    upper: float,
    tolerance: float,
    maximum_iterations: int,
) -> float | None:
    """Find the base fidelity where exactly k rounds first reach a threshold."""
    if fidelity_after_rounds(lower, rounds) >= required_fidelity:
        return lower
    if fidelity_after_rounds(upper, rounds) < required_fidelity:
        return None
    low, high = lower, upper
    for _ in range(maximum_iterations):
        middle = (low + high) / 2.0
        if fidelity_after_rounds(middle, rounds) < required_fidelity:
            low = middle
        else:
            high = middle
        if high - low <= tolerance:
            break
    return high


def _best_evaluation(
    evaluations: Iterable[LinkConfigurationEvaluation],
) -> LinkConfigurationEvaluation | None:
    feasible = [evaluation for evaluation in evaluations if evaluation.feasible]
    return min(
        feasible,
        key=lambda evaluation: (
            -evaluation.effective_rate,
            evaluation.total_purification_rounds,
            evaluation.fidelity,
        ),
        default=None,
    )


def search_link_configuration(
    channel: QuantumChannel,
    requirements: Sequence[Tuple[Request, float]],
    link_config: LinkConfig,
    search_config: LinkConfigurationSearchConfig,
    maximum_purification_rounds: int,
) -> LinkConfigurationDecision:
    """Coarse search, threshold bisection, then 0.001 local refinement."""
    if search_config.use_precomputed_lookup:
        return search_link_configuration_with_lookup(
            channel,
            requirements,
            link_config,
            search_config,
            maximum_purification_rounds,
        )
    lower = link_config.minimum_fidelity
    upper = link_config.maximum_fidelity
    evaluated: Dict[float, LinkConfigurationEvaluation] = {}

    def evaluate_points(points: Iterable[float]) -> None:
        for point in points:
            fidelity = _quantize(point, search_config.fine_step, lower, upper)
            if fidelity not in evaluated:
                evaluated[fidelity] = evaluate_link_configuration(
                    channel,
                    requirements,
                    fidelity,
                    maximum_purification_rounds,
                )

    coarse_points = _grid(lower, upper, search_config.coarse_step)
    evaluate_points(coarse_points)
    ranked_coarse = sorted(
        (evaluated[_quantize(point, search_config.fine_step, lower, upper)] for point in coarse_points),
        key=lambda evaluation: (
            not evaluation.feasible,
            -evaluation.effective_rate,
            evaluation.total_purification_rounds,
            evaluation.fidelity,
        ),
    )
    retained = [
        evaluation for evaluation in ranked_coarse if evaluation.feasible
    ][:search_config.retained_coarse_regions]
    for evaluation in retained:
        evaluate_points(_grid(
            max(lower, evaluation.fidelity - search_config.coarse_step),
            min(upper, evaluation.fidelity + search_config.coarse_step),
            search_config.fine_step,
        ))

    threshold_points = []
    for _, required_fidelity in requirements:
        for rounds in range(maximum_purification_rounds + 1):
            threshold = _purification_threshold(
                required_fidelity,
                rounds,
                lower,
                upper,
                search_config.threshold_tolerance,
                search_config.maximum_threshold_iterations,
            )
            if threshold is not None:
                threshold_points.extend((
                    threshold - search_config.fine_step,
                    threshold,
                    threshold + search_config.fine_step,
                ))
    evaluate_points(threshold_points)

    selected = _best_evaluation(evaluated.values())
    if selected is not None:
        channel.active_profile_index = None
        channel.fidelity = selected.fidelity
        channel.raw_entanglement_rate = selected.raw_rate
        channel.bandwidth = selected.raw_rate
        channel.selected_configuration = selected
    return LinkConfigurationDecision(
        channel=channel,
        selected=selected,
        evaluated_count=len(evaluated),
        feasible_count=sum(evaluation.feasible for evaluation in evaluated.values()),
    )


def select_all_link_configurations(
    quality_result: QualityAllocationResult,
    link_config: LinkConfig,
    search_config: LinkConfigurationSearchConfig,
    maximum_purification_rounds: int,
) -> LinkConfigurationResult:
    """Select a common configuration for every link on a fixed active path."""
    requirements = collect_link_requirements(quality_result)
    decisions = {
        channel: search_link_configuration(
            channel,
            channel_requirements,
            link_config,
            search_config,
            maximum_purification_rounds,
        )
        for channel, channel_requirements in requirements.items()
    }
    return LinkConfigurationResult(decisions)

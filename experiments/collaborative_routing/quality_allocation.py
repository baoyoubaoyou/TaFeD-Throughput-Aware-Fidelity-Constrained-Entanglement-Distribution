"""Stage I-A: map end-to-end fidelity targets to per-link requirements."""

import math
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from qns.entity.node.node import QNode
from qns.entity.qchannel.qchannel import QuantumChannel
from qns.network.network import QuantumNetwork
from qns.network.requests import Request

from experiments.collaborative_routing.config import QualityAllocationConfig
from experiments.collaborative_routing.purification import fidelity_after_rounds
from experiments.collaborative_routing.quality_models import (
    CandidatePathQualityPlan,
    LinkQualityState,
    QualityAllocationResult,
    RequestQualityPlan,
)
from experiments.collaborative_routing.quality_price import InitialQualityPriceModel, QualityPriceModel


def werner_parameter(fidelity: float) -> float:
    """Convert Werner-state fidelity to its multiplicative parameter."""
    if not 0.25 < fidelity <= 1.0:
        raise ValueError("Werner fidelity must be in (0.25, 1]")
    return (4.0 * fidelity - 1.0) / 3.0


def calculate_link_fidelity_bounds(
    channel: QuantumChannel,
    maximum_purification_rounds: int,
) -> Tuple[float, float]:
    """Return the request-level fidelity envelope supported by a link."""
    table = getattr(channel, "fidelity_rate_table", None)
    if not table:
        raise ValueError(f"channel {channel} does not have a fidelity-rate table")
    base_fidelities = [float(point["fidelity"]) for point in table]
    lower = min(base_fidelities)
    upper = max(
        fidelity_after_rounds(fidelity, maximum_purification_rounds)
        for fidelity in base_fidelities
    )
    return lower, upper


def build_link_quality_states(
    network: QuantumNetwork,
    maximum_purification_rounds: int,
    price_config: Optional[QualityAllocationConfig] = None,
    price_model: Optional[QualityPriceModel] = None,
    link_loads: Optional[Mapping[QuantumChannel, float]] = None,
    quality_prices: Optional[Mapping[QuantumChannel, float]] = None,
    channels: Optional[Sequence[QuantumChannel]] = None,
) -> Dict[QuantumChannel, LinkQualityState]:
    """Build reusable link bounds and prices for one stage-I-A iteration.

    ``quality_prices`` has highest priority and is the interface used by stage
    I-B to feed updated prices back into the same allocation solver.
    """
    channel_list = list(network.qchannels if channels is None else channels)
    bounds = {
        channel: calculate_link_fidelity_bounds(channel, maximum_purification_rounds)
        for channel in channel_list
    }
    upper_fidelities = {channel: bound[1] for channel, bound in bounds.items()}

    if quality_prices is None:
        config = price_config or QualityAllocationConfig()
        model = price_model or InitialQualityPriceModel(config)
        all_prices = model.calculate(network, upper_fidelities, link_loads)
        prices = {channel: all_prices[channel] for channel in channel_list}
    else:
        prices = dict(quality_prices)

    states = {}
    for channel, (lower, upper) in bounds.items():
        price = float(prices.get(channel, 0.0))
        if not math.isfinite(price) or price <= 0:
            raise ValueError(f"quality price for {channel} must be finite and positive")
        states[channel] = LinkQualityState(channel, lower, upper, price)
    return states


def calculate_quality_budget(required_fidelity: float, path: Sequence[QNode]) -> float:
    """Return B_r after subtracting successful-swap quality factors."""
    if len(path) < 2:
        raise ValueError("a candidate path must contain at least two nodes")
    budget = math.log(werner_parameter(required_fidelity))
    for node in path[1:-1]:
        quality_factor = float(getattr(node, "swap_quality_factor", 1.0))
        if not 0 < quality_factor <= 1.0:
            raise ValueError(f"invalid swap quality factor on {node}")
        budget -= math.log(quality_factor)
    return budget


def calculate_end_to_end_fidelity(
    path: Sequence[QNode],
    channels: Sequence[QuantumChannel],
    fidelity_requirements: Mapping[QuantumChannel, float],
) -> float:
    """Recompute end-to-end fidelity from a candidate allocation."""
    log_quality = 0.0
    for channel in channels:
        log_quality += math.log(werner_parameter(fidelity_requirements[channel]))
    for node in path[1:-1]:
        quality_factor = float(getattr(node, "swap_quality_factor", 1.0))
        if not 0 < quality_factor <= 1.0:
            raise ValueError(f"invalid swap quality factor on {node}")
        log_quality += math.log(quality_factor)
    end_to_end_w = math.exp(log_quality)
    return (1.0 + 3.0 * end_to_end_w) / 4.0


def _resolve_path_channels(path: Sequence[QNode]) -> List[QuantumChannel]:
    if len(set(path)) != len(path):
        raise ValueError("candidate paths must be loopless")
    channels = []
    for node, next_node in zip(path, path[1:]):
        channel = node.get_qchannel(next_node)
        if channel is None:
            raise ValueError(f"no quantum channel connects {node} and {next_node}")
        channels.append(channel)
    return channels


def _requirements_at_water_level(
    channels: Sequence[QuantumChannel],
    link_states: Mapping[QuantumChannel, LinkQualityState],
    water_level: float,
) -> Dict[QuantumChannel, float]:
    requirements = {}
    for channel in channels:
        state = link_states[channel]
        unconstrained = 0.25 + water_level / state.quality_price
        requirements[channel] = min(
            state.upper_fidelity,
            max(state.lower_fidelity, unconstrained),
        )
    return requirements


def _log_link_quality(requirements: Mapping[QuantumChannel, float]) -> float:
    return sum(math.log(werner_parameter(fidelity)) for fidelity in requirements.values())


def _make_feasible_plan(
    candidate_index: int,
    path: List[QNode],
    channels: List[QuantumChannel],
    link_states: Mapping[QuantumChannel, LinkQualityState],
    quality_budget: float,
    requirements: Dict[QuantumChannel, float],
    required_fidelity: float,
    status: str,
    water_level: float,
    iterations: int,
    tolerance: float,
) -> CandidatePathQualityPlan:
    quality_cost = sum(
        link_states[channel].quality_price * requirements[channel]
        for channel in channels
    )
    incremental_cost = sum(
        link_states[channel].quality_price
        * (requirements[channel] - link_states[channel].lower_fidelity)
        for channel in channels
    )
    achieved_fidelity = calculate_end_to_end_fidelity(path, channels, requirements)
    if achieved_fidelity + tolerance < required_fidelity:
        return CandidatePathQualityPlan(
            candidate_index=candidate_index,
            path=path,
            channels=channels,
            feasible=False,
            status="numerical_validation_failed",
            quality_budget=quality_budget,
            failure_reason=(
                f"recomputed fidelity {achieved_fidelity} is below target {required_fidelity}"
            ),
        )
    return CandidatePathQualityPlan(
        candidate_index=candidate_index,
        path=path,
        channels=channels,
        feasible=True,
        status=status,
        quality_budget=quality_budget,
        fidelity_requirements=requirements,
        quality_cost=quality_cost,
        incremental_quality_cost=incremental_cost,
        achieved_fidelity=achieved_fidelity,
        water_level=water_level,
        iterations=iterations,
    )


def solve_path_fidelity_allocation(
    path: Sequence[QNode],
    required_fidelity: float,
    link_states: Mapping[QuantumChannel, LinkQualityState],
    candidate_index: int = 0,
    tolerance: float = 1e-10,
    maximum_iterations: int = 100,
) -> CandidatePathQualityPlan:
    """Solve the convex request-level allocation on one fixed path.

    The KKT solution is
    ``f_e(nu) = clip(1/4 + nu/lambda_e, lower_e, upper_e)``.
    A monotone bisection finds the water level ``nu``.
    """
    path = list(path)
    try:
        channels = _resolve_path_channels(path)
        budget = calculate_quality_budget(required_fidelity, path)
    except ValueError as error:
        return CandidatePathQualityPlan(
            candidate_index,
            path,
            [],
            False,
            "invalid_path",
            float("nan"),
            failure_reason=str(error),
        )

    missing = [channel for channel in channels if channel not in link_states]
    if missing:
        raise KeyError(f"missing quality state for channels: {missing}")

    lower_requirements = {
        channel: link_states[channel].lower_fidelity for channel in channels
    }
    upper_requirements = {
        channel: link_states[channel].upper_fidelity for channel in channels
    }
    lower_quality = _log_link_quality(lower_requirements)
    upper_quality = _log_link_quality(upper_requirements)

    if upper_quality + tolerance < budget:
        return CandidatePathQualityPlan(
            candidate_index=candidate_index,
            path=path,
            channels=channels,
            feasible=False,
            status="quality_infeasible",
            quality_budget=budget,
            failure_reason="path upper fidelity envelope cannot meet the request target",
        )

    if lower_quality + tolerance >= budget:
        return _make_feasible_plan(
            candidate_index,
            path,
            channels,
            link_states,
            budget,
            lower_requirements,
            required_fidelity,
            "lower_bounds_sufficient",
            0.0,
            0,
            tolerance,
        )

    low = 0.0
    high = max(
        link_states[channel].quality_price
        * (link_states[channel].upper_fidelity - 0.25)
        for channel in channels
    )
    iterations = 0
    for iterations in range(1, maximum_iterations + 1):
        middle = (low + high) / 2.0
        requirements = _requirements_at_water_level(channels, link_states, middle)
        achieved_quality = _log_link_quality(requirements)
        if achieved_quality < budget:
            low = middle
        else:
            high = middle
        if abs(achieved_quality - budget) <= tolerance:
            break

    # Use the feasible side of the final bracket so numerical round-off never
    # returns a solution just below the requested fidelity.
    requirements = _requirements_at_water_level(channels, link_states, high)
    return _make_feasible_plan(
        candidate_index,
        path,
        channels,
        link_states,
        budget,
        requirements,
        required_fidelity,
        "allocated",
        high,
        iterations,
        tolerance,
    )


def _extract_path(candidate_route) -> List[QNode]:
    if isinstance(candidate_route, tuple) and len(candidate_route) >= 3:
        return list(candidate_route[2])
    if isinstance(candidate_route, list) and candidate_route and isinstance(candidate_route[0], QNode):
        return list(candidate_route)
    raise ValueError("candidate route must be a SimQN route tuple or a node list")


def allocate_request_quality(
    request: Request,
    link_states: Mapping[QuantumChannel, LinkQualityState],
    tolerance: float = 1e-10,
    maximum_iterations: int = 100,
    mutate_request: bool = True,
) -> RequestQualityPlan:
    """Evaluate all saved candidate paths and activate the cheapest feasible one."""
    required_fidelity = float(request.attr["required_fidelity"])
    candidates = request.attr.get("candidate_routes", [])
    candidate_plans = []
    for index, candidate in enumerate(candidates):
        try:
            path = _extract_path(candidate)
            plan = solve_path_fidelity_allocation(
                path,
                required_fidelity,
                link_states,
                candidate_index=index,
                tolerance=tolerance,
                maximum_iterations=maximum_iterations,
            )
        except ValueError as error:
            plan = CandidatePathQualityPlan(
                index,
                [],
                [],
                False,
                "invalid_path",
                float("nan"),
                failure_reason=str(error),
            )
        candidate_plans.append(plan)

    feasible_plans = [plan for plan in candidate_plans if plan.feasible]
    selected = min(
        feasible_plans,
        key=lambda plan: (
            plan.quality_cost,
            plan.incremental_quality_cost,
            plan.hop_count,
            plan.candidate_index,
        ),
        default=None,
    )
    result = RequestQualityPlan(
        request=request,
        candidate_plans=candidate_plans,
        selected_candidate_index=None if selected is None else selected.candidate_index,
    )

    if mutate_request:
        _store_request_result(request, result)
    return result


def _store_request_result(request: Request, result: RequestQualityPlan) -> None:
    selected = result.selected_plan
    request.attr["quality_candidate_plans"] = result.candidate_plans
    if selected is None:
        request.attr.update({
            "selected_route_index": None,
            "selected_route": None,
            "selected_path": None,
            "backup_routes": list(request.attr.get("candidate_routes", [])),
            "link_fidelity_requirements": {},
            "quality_cost": None,
            "quality_status": "quality_rejected",
        })
        return

    candidates = request.attr["candidate_routes"]
    request.attr.update({
        "selected_route_index": selected.candidate_index,
        "selected_route": candidates[selected.candidate_index],
        "selected_path": selected.path,
        "backup_routes": [
            candidate for index, candidate in enumerate(candidates)
            if index != selected.candidate_index
        ],
        "link_fidelity_requirements": {
            channel.name: fidelity
            for channel, fidelity in selected.fidelity_requirements.items()
        },
        "quality_cost": selected.quality_cost,
        "achieved_fidelity": selected.achieved_fidelity,
        "quality_status": "selected",
    })


def store_quality_allocation_result(result: QualityAllocationResult) -> None:
    """Publish an already selected allocation result to its SimQN requests."""
    for request_plan in result.request_plans:
        _store_request_result(request_plan.request, request_plan)


def allocate_all_request_qualities(
    network: QuantumNetwork,
    requests: Optional[Sequence[Request]] = None,
    maximum_purification_rounds: int = 6,
    solver_config: Optional[QualityAllocationConfig] = None,
    price_model: Optional[QualityPriceModel] = None,
    link_loads: Optional[Mapping[QuantumChannel, float]] = None,
    quality_prices: Optional[Mapping[QuantumChannel, float]] = None,
    mutate_requests: bool = True,
) -> QualityAllocationResult:
    """Run one complete stage-I-A pass for all requests.

    Later stage-I-B iterations can call this function again with
    ``quality_prices`` containing the updated :math:`lambda_e^Q` values.
    """
    solver_config = solver_config or QualityAllocationConfig()
    request_list = list(network.requests if requests is None else requests)
    states = build_link_quality_states(
        network,
        maximum_purification_rounds,
        price_config=solver_config,
        price_model=price_model,
        link_loads=link_loads,
        quality_prices=quality_prices,
    )
    plans = [
        allocate_request_quality(
            request,
            states,
            tolerance=solver_config.tolerance,
            maximum_iterations=solver_config.maximum_bisection_iterations,
            mutate_request=mutate_requests,
        )
        for request in request_list
    ]
    return QualityAllocationResult(states, plans)


def allocate_fixed_path_request_quality(
    request: Request,
    link_states: Mapping[QuantumChannel, LinkQualityState],
    tolerance: float = 1e-10,
    maximum_iterations: int = 100,
    mutate_request: bool = True,
) -> RequestQualityPlan:
    """Reallocate quality on the path selected in the first stage-I round."""
    path = request.attr.get("selected_path")
    candidate_index = request.attr.get("selected_route_index")
    if path is None or candidate_index is None:
        raise ValueError("request does not have a selected path to keep fixed")

    plan = solve_path_fidelity_allocation(
        path,
        float(request.attr["required_fidelity"]),
        link_states,
        candidate_index=int(candidate_index),
        tolerance=tolerance,
        maximum_iterations=maximum_iterations,
    )
    result = RequestQualityPlan(
        request=request,
        candidate_plans=[plan],
        selected_candidate_index=plan.candidate_index if plan.feasible else None,
    )
    if mutate_request:
        _store_request_result(request, result)
    return result


def allocate_fixed_path_qualities(
    network: QuantumNetwork,
    requests: Optional[Sequence[Request]] = None,
    maximum_purification_rounds: int = 6,
    solver_config: Optional[QualityAllocationConfig] = None,
    quality_prices: Optional[Mapping[QuantumChannel, float]] = None,
    active_channels: Optional[Sequence[QuantumChannel]] = None,
    mutate_requests: bool = True,
) -> QualityAllocationResult:
    """Run stage I-A again without reconsidering the saved K candidate paths."""
    solver_config = solver_config or QualityAllocationConfig()
    request_list = list(network.requests if requests is None else requests)
    states = build_link_quality_states(
        network,
        maximum_purification_rounds,
        price_config=solver_config,
        quality_prices=quality_prices,
        channels=active_channels,
    )
    plans = [
        allocate_fixed_path_request_quality(
            request,
            states,
            tolerance=solver_config.tolerance,
            maximum_iterations=solver_config.maximum_bisection_iterations,
            mutate_request=mutate_requests,
        )
        for request in request_list
    ]
    return QualityAllocationResult(states, plans)


def allocate_scenario_qualities(scenario, mutate_requests: bool = True) -> QualityAllocationResult:
    """Convenience wrapper using an experiment scenario's configured values."""
    return allocate_all_request_qualities(
        scenario.network,
        requests=scenario.requests,
        maximum_purification_rounds=scenario.config.purification.maximum_rounds,
        solver_config=scenario.config.quality_allocation,
        mutate_requests=mutate_requests,
    )

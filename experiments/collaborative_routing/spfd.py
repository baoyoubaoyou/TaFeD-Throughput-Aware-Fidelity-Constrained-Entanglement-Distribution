"""Two-stage SPFD baseline from the INFOCOM 2025 link-configuration paper.

Only the two components needed by this project are reproduced:

1. split an end-to-end Werner-quality requirement equally over a fixed path;
2. let every active link greedily choose its configuration independently.

The common K-shortest-path selector is reused before SPFD starts.  Swapping,
end-to-end scheduling, and the paper's later Bayesian optimization are outside
the scope of this baseline.
"""

from dataclasses import dataclass, field
import math
from typing import Dict, List, Optional, Sequence

from qns.entity.qchannel.qchannel import QuantumChannel
from qns.network.requests import Request

from experiments.collaborative_routing.configuration_models import (
    LinkConfigurationDecision,
    LinkConfigurationResult,
)
from experiments.collaborative_routing.link_configuration import (
    evaluate_lookup_configuration,
    memory_limited_raw_rate,
    raw_entanglement_rate,
)
from experiments.collaborative_routing.purification_lookup import (
    PurificationLookupPlan,
    PurificationLookupPoint,
    build_werner_purification_lookup,
    find_minimum_lookup_plan,
)
from experiments.collaborative_routing.quality_allocation import (
    allocate_scenario_qualities,
    calculate_end_to_end_fidelity,
    store_quality_allocation_result,
    werner_parameter,
)
from experiments.collaborative_routing.quality_models import (
    CandidatePathQualityPlan,
    QualityAllocationResult,
    RequestQualityPlan,
)


@dataclass(frozen=True)
class SPFDLinkDemand:
    """One request's equally split fidelity requirement on one link."""

    request: Request
    required_fidelity: float
    required_log_werner: float
    demand_rate: float


@dataclass(frozen=True)
class SPFDGreedyAllocation:
    """Resource assigned to one request while evaluating one link point."""

    demand: SPFDLinkDemand
    rounds: int
    output_fidelity: float
    expected_raw_pairs: float
    memory_slots_per_endpoint: int
    served_rate: float
    raw_rate_consumed: float


@dataclass
class SPFDGreedyEvaluation:
    """Paper-style greedy evaluation of one candidate link configuration."""

    channel: QuantumChannel
    fidelity: float
    raw_rate: float
    feasible: bool
    total_served_rate: float = 0.0
    minimum_served_rate: float = 0.0
    remaining_raw_rate: float = 0.0
    total_purification_rounds: int = 0
    allocations: List[SPFDGreedyAllocation] = field(default_factory=list)
    failure_reason: Optional[str] = None


@dataclass
class SPFDLinkDecision:
    """All candidate evaluations and the independently selected link point."""

    channel: QuantumChannel
    candidates: List[SPFDGreedyEvaluation]
    selected: Optional[SPFDGreedyEvaluation]

    @property
    def feasible(self) -> bool:
        return self.selected is not None


@dataclass
class SPFDResult:
    """Output of the equal-split and independent-greedy SPFD baseline."""

    quality_result: QualityAllocationResult
    link_demands: Dict[QuantumChannel, List[SPFDLinkDemand]]
    greedy_decisions: Dict[QuantumChannel, SPFDLinkDecision]
    configuration_result: LinkConfigurationResult

    @property
    def active_links(self) -> int:
        return len(self.greedy_decisions)

    @property
    def infeasible_links(self) -> int:
        return sum(not decision.feasible for decision in self.greedy_decisions.values())

    @property
    def link_effective_rates(self) -> Dict[QuantumChannel, float]:
        """Return rates under the same metric used by the joint algorithm."""
        return {
            channel: decision.selected.effective_rate
            for channel, decision in self.configuration_result.decisions.items()
            if decision.selected is not None
        }

    @property
    def total_link_rate(self) -> float:
        rates = self.link_effective_rates.values()
        return sum(rates) if self.infeasible_links == 0 else 0.0

    @property
    def minimum_link_rate(self) -> float:
        rates = list(self.link_effective_rates.values())
        if self.infeasible_links or not rates:
            return 0.0
        return min(rates)

    @property
    def average_link_rate(self) -> float:
        rates = list(self.link_effective_rates.values())
        if self.infeasible_links or not rates:
            return 0.0
        return sum(rates) / len(rates)

    @property
    def link_rate_fairness(self) -> float:
        """Jain fairness of effective rates over active links."""
        rates = list(self.link_effective_rates.values())
        squared_sum = sum(rate * rate for rate in rates)
        if self.infeasible_links or not rates or squared_sum <= 0:
            return 0.0
        return sum(rates) ** 2 / (len(rates) * squared_sum)

    @property
    def total_greedy_served_rate(self) -> float:
        """Return the original SPFD per-link selection objective for diagnosis."""
        if self.infeasible_links:
            return 0.0
        return sum(
            decision.selected.total_served_rate
            for decision in self.greedy_decisions.values()
            if decision.selected is not None
        )


def fidelity_from_werner_parameter(parameter: float) -> float:
    """Convert a Werner parameter to fidelity."""
    if not 0.0 < parameter <= 1.0:
        raise ValueError("Werner parameter must be in (0, 1]")
    return (1.0 + 3.0 * parameter) / 4.0


def spfd_equal_link_fidelity(required_fidelity: float, hop_count: int) -> float:
    """Apply SPFD's equal split in the logarithmic Werner domain."""
    if hop_count < 1:
        raise ValueError("hop_count must be positive")
    request_werner = werner_parameter(required_fidelity)
    return fidelity_from_werner_parameter(request_werner ** (1.0 / hop_count))


def allocate_spfd_equal_requirements(
    scenario,
    path_quality_result: Optional[QualityAllocationResult] = None,
    mutate_requests: bool = True,
) -> QualityAllocationResult:
    """Run SPFD stage one on paths chosen by the common K-shortest selector.

    Passing ``path_quality_result`` is useful in paired experiments: it makes
    SPFD consume exactly the paths already selected for the joint algorithm.
    When omitted, the project's normal K-shortest quality-cost selector runs
    once to fix a path for every request before the equal split is applied.
    """
    path_quality_result = path_quality_result or allocate_scenario_qualities(
        scenario,
        mutate_requests=mutate_requests,
    )
    request_plans = []
    for path_plan in path_quality_result.request_plans:
        selected_path = path_plan.selected_plan
        if selected_path is None:
            request_plans.append(RequestQualityPlan(
                request=path_plan.request,
                candidate_plans=[],
                selected_candidate_index=None,
            ))
            continue

        link_fidelity = spfd_equal_link_fidelity(
            float(path_plan.request.attr["required_fidelity"]),
            selected_path.hop_count,
        )
        requirements = {
            channel: link_fidelity for channel in selected_path.channels
        }
        achieved_fidelity = calculate_end_to_end_fidelity(
            selected_path.path,
            selected_path.channels,
            requirements,
        )
        equal_plan = CandidatePathQualityPlan(
            candidate_index=selected_path.candidate_index,
            path=list(selected_path.path),
            channels=list(selected_path.channels),
            feasible=True,
            status="spfd_equal_split",
            quality_budget=selected_path.quality_budget,
            fidelity_requirements=requirements,
            quality_cost=sum(
                path_quality_result.link_states[channel].quality_price * link_fidelity
                for channel in selected_path.channels
            ),
            incremental_quality_cost=0.0,
            achieved_fidelity=achieved_fidelity,
            iterations=0,
        )
        request_plans.append(RequestQualityPlan(
            request=path_plan.request,
            candidate_plans=[equal_plan],
            selected_candidate_index=equal_plan.candidate_index,
        ))

    result = QualityAllocationResult(path_quality_result.link_states, request_plans)
    if mutate_requests:
        store_quality_allocation_result(result)
        for request_plan in result.request_plans:
            selected = request_plan.selected_plan
            request_plan.request.attr["spfd_link_fidelity_requirements"] = (
                {} if selected is None else {
                    channel.name: fidelity
                    for channel, fidelity in selected.fidelity_requirements.items()
                }
            )
    return result


def collect_spfd_link_demands(
    quality_result: QualityAllocationResult,
) -> Dict[QuantumChannel, List[SPFDLinkDemand]]:
    """Build the paper's per-link request dictionary in request order."""
    grouped: Dict[QuantumChannel, List[SPFDLinkDemand]] = {}
    for request_plan in quality_result.request_plans:
        selected = request_plan.selected_plan
        if selected is None:
            continue
        demand_rate = float(request_plan.request.attr["demand_intensity"])
        for channel, required_fidelity in selected.fidelity_requirements.items():
            grouped.setdefault(channel, []).append(SPFDLinkDemand(
                request=request_plan.request,
                required_fidelity=float(required_fidelity),
                required_log_werner=math.log(werner_parameter(required_fidelity)),
                demand_rate=demand_rate,
            ))
    return grouped


def _endpoint_memory(channel: QuantumChannel) -> int:
    capacities = [
        sum(int(memory.capacity) for memory in node.memories)
        for node in channel.node_list
    ]
    return min(capacities) if capacities else 0


def _nearest_lookup_point(
    fidelity: float,
    lookup: Sequence[PurificationLookupPoint],
) -> PurificationLookupPoint:
    """Round an original SPFD candidate to the configured fidelity precision."""
    return min(lookup, key=lambda point: (abs(point.fidelity - fidelity), point.fidelity))


def _candidate_points(
    demands: Sequence[SPFDLinkDemand],
    lookup: Sequence[PurificationLookupPoint],
) -> List[PurificationLookupPoint]:
    # Algorithm 1 appends request-derived points to M_e and retains the first
    # point when objectives tie.  Preserve that insertion order here.
    points = []
    seen = set()
    for demand in demands:
        point = _nearest_lookup_point(demand.required_fidelity, lookup)
        if point.fidelity not in seen:
            points.append(point)
            seen.add(point.fidelity)
    return points


def evaluate_spfd_greedy_candidate(
    channel: QuantumChannel,
    demands: Sequence[SPFDLinkDemand],
    point: PurificationLookupPoint,
) -> SPFDGreedyEvaluation:
    """Evaluate one candidate using Algorithm 1's sequential allocation."""
    raw_rate = raw_entanglement_rate(channel, point.fidelity)
    remaining = memory_limited_raw_rate(channel, raw_rate)
    memory_capacity = _endpoint_memory(channel)
    allocations = []
    for demand in demands:
        plan: Optional[PurificationLookupPlan] = find_minimum_lookup_plan(
            point,
            demand.required_fidelity,
        )
        if plan is None:
            return SPFDGreedyEvaluation(
                channel=channel,
                fidelity=point.fidelity,
                raw_rate=raw_rate,
                feasible=False,
                remaining_raw_rate=remaining,
                failure_reason="quality target exceeds the maximum purification depth",
            )
        if plan.memory_slots_per_endpoint > memory_capacity:
            return SPFDGreedyEvaluation(
                channel=channel,
                fidelity=point.fidelity,
                raw_rate=raw_rate,
                feasible=False,
                remaining_raw_rate=remaining,
                failure_reason=(
                    f"purification needs {plan.memory_slots_per_endpoint} memory slots "
                    f"but only {memory_capacity} are available per endpoint"
                ),
            )
        served_rate = min(
            demand.demand_rate,
            remaining / plan.expected_raw_pairs,
        )
        consumed = served_rate * plan.expected_raw_pairs
        remaining = max(0.0, remaining - consumed)
        allocations.append(SPFDGreedyAllocation(
            demand=demand,
            rounds=plan.rounds,
            output_fidelity=plan.output_fidelity,
            expected_raw_pairs=plan.expected_raw_pairs,
            memory_slots_per_endpoint=plan.memory_slots_per_endpoint,
            served_rate=served_rate,
            raw_rate_consumed=consumed,
        ))

    served_rates = [allocation.served_rate for allocation in allocations]
    return SPFDGreedyEvaluation(
        channel=channel,
        fidelity=point.fidelity,
        raw_rate=raw_rate,
        feasible=True,
        total_served_rate=sum(served_rates),
        minimum_served_rate=min(served_rates, default=0.0),
        remaining_raw_rate=remaining,
        total_purification_rounds=sum(item.rounds for item in allocations),
        allocations=allocations,
    )


def select_spfd_link_configuration(
    channel: QuantumChannel,
    demands: Sequence[SPFDLinkDemand],
    lookup: Sequence[PurificationLookupPoint],
) -> SPFDLinkDecision:
    """Apply SPFD stage two independently to one active link."""
    evaluations = [
        evaluate_spfd_greedy_candidate(channel, demands, point)
        for point in _candidate_points(demands, lookup)
    ]
    feasible = [evaluation for evaluation in evaluations if evaluation.feasible]
    selected = max(
        feasible,
        key=lambda evaluation: evaluation.total_served_rate,
        default=None,
    )
    return SPFDLinkDecision(channel, evaluations, selected)


def _store_spfd_results(result: SPFDResult) -> None:
    for channel, decision in result.greedy_decisions.items():
        if decision.selected is None:
            continue
        common = result.configuration_result.decisions[channel].selected
        channel.spfd_greedy_configuration = decision.selected
        if common is not None:
            channel.active_profile_index = None
            channel.fidelity = common.fidelity
            channel.raw_entanglement_rate = common.raw_rate
            channel.bandwidth = common.raw_rate
            channel.selected_configuration = common
        for allocation in decision.selected.allocations:
            per_link = allocation.demand.request.attr.setdefault(
                "spfd_purification_decisions",
                {},
            )
            per_link[channel.name] = {
                "required_fidelity": allocation.demand.required_fidelity,
                "base_fidelity": decision.selected.fidelity,
                "raw_rate": decision.selected.raw_rate,
                "purification_rounds": allocation.rounds,
                "output_fidelity": allocation.output_fidelity,
                "expected_raw_pairs": allocation.expected_raw_pairs,
                "served_rate": allocation.served_rate,
            }


def run_spfd_two_stage(
    scenario,
    path_quality_result: Optional[QualityAllocationResult] = None,
    mutate_requests: bool = True,
) -> SPFDResult:
    """Run the requested SPFD two-stage baseline on a SimQN scenario."""
    quality_result = allocate_spfd_equal_requirements(
        scenario,
        path_quality_result=path_quality_result,
        mutate_requests=mutate_requests,
    )
    demands = collect_spfd_link_demands(quality_result)
    lookup = build_werner_purification_lookup(
        scenario.config.links.minimum_fidelity,
        scenario.config.links.maximum_fidelity,
        scenario.config.link_configuration_search.fine_step,
        scenario.config.purification.maximum_rounds,
    )
    greedy_decisions = {
        channel: select_spfd_link_configuration(channel, channel_demands, lookup)
        for channel, channel_demands in demands.items()
    }

    configuration_decisions = {}
    point_by_fidelity = {point.fidelity: point for point in lookup}
    for channel, greedy_decision in greedy_decisions.items():
        selected = greedy_decision.selected
        common_evaluation = None
        if selected is not None:
            common_evaluation = evaluate_lookup_configuration(
                channel,
                [
                    (demand.request, demand.required_fidelity)
                    for demand in demands[channel]
                ],
                point_by_fidelity[selected.fidelity],
            )
            if not common_evaluation.feasible:
                common_evaluation = None
        configuration_decisions[channel] = LinkConfigurationDecision(
            channel=channel,
            selected=common_evaluation,
            evaluated_count=len(greedy_decision.candidates),
            feasible_count=sum(
                candidate.feasible for candidate in greedy_decision.candidates
            ),
        )

    result = SPFDResult(
        quality_result=quality_result,
        link_demands=demands,
        greedy_decisions=greedy_decisions,
        configuration_result=LinkConfigurationResult(configuration_decisions),
    )
    if mutate_requests:
        _store_spfd_results(result)
    return result

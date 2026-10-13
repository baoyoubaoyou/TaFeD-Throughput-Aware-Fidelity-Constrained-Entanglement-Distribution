"""Data contracts for request-level link-fidelity allocation."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from qns.entity.node.node import QNode
from qns.entity.qchannel.qchannel import QuantumChannel
from qns.network.requests import Request


@dataclass(frozen=True)
class LinkQualityState:
    channel: QuantumChannel
    lower_fidelity: float
    upper_fidelity: float
    quality_price: float


@dataclass
class CandidatePathQualityPlan:
    candidate_index: int
    path: List[QNode]
    channels: List[QuantumChannel]
    feasible: bool
    status: str
    quality_budget: float
    fidelity_requirements: Dict[QuantumChannel, float] = field(default_factory=dict)
    quality_cost: float = float("inf")
    incremental_quality_cost: float = float("inf")
    achieved_fidelity: Optional[float] = None
    water_level: Optional[float] = None
    iterations: int = 0
    failure_reason: Optional[str] = None

    @property
    def hop_count(self) -> int:
        return len(self.path) - 1


@dataclass
class RequestQualityPlan:
    request: Request
    candidate_plans: List[CandidatePathQualityPlan]
    selected_candidate_index: Optional[int]

    @property
    def selected_plan(self) -> Optional[CandidatePathQualityPlan]:
        if self.selected_candidate_index is None:
            return None
        for plan in self.candidate_plans:
            if plan.candidate_index == self.selected_candidate_index:
                return plan
        return None

    @property
    def feasible(self) -> bool:
        return self.selected_plan is not None


@dataclass
class QualityAllocationResult:
    link_states: Dict[QuantumChannel, LinkQualityState]
    request_plans: List[RequestQualityPlan]

    @property
    def accepted_requests(self) -> int:
        return sum(plan.feasible for plan in self.request_plans)

    @property
    def acceptance_rate(self) -> float:
        if not self.request_plans:
            return 0.0
        return self.accepted_requests / len(self.request_plans)

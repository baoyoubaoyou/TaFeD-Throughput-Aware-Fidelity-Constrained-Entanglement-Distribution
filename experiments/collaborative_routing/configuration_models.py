"""Data contracts for stage I-B and the joint stage-I iteration."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from qns.entity.qchannel.qchannel import QuantumChannel
from qns.network.requests import Request

from experiments.collaborative_routing.quality_models import QualityAllocationResult


@dataclass(frozen=True)
class RequestPurificationDecision:
    request: Request
    required_fidelity: float
    demand_weight: float
    rounds: int
    output_fidelity: float
    expected_raw_pairs: float
    memory_slots_per_endpoint: int


@dataclass
class LinkConfigurationEvaluation:
    channel: QuantumChannel
    fidelity: float
    feasible: bool
    raw_rate: float
    effective_rate: float = 0.0
    average_raw_pairs: float = float("inf")
    total_purification_rounds: int = 0
    request_decisions: List[RequestPurificationDecision] = field(default_factory=list)
    failure_reason: Optional[str] = None


@dataclass
class LinkConfigurationDecision:
    channel: QuantumChannel
    selected: Optional[LinkConfigurationEvaluation]
    evaluated_count: int
    feasible_count: int

    @property
    def feasible(self) -> bool:
        return self.selected is not None


@dataclass
class LinkConfigurationResult:
    decisions: Dict[QuantumChannel, LinkConfigurationDecision]

    @property
    def active_links(self) -> int:
        return len(self.decisions)

    @property
    def infeasible_links(self) -> int:
        return sum(not decision.feasible for decision in self.decisions.values())

    @property
    def total_effective_rate(self) -> float:
        return sum(
            decision.selected.effective_rate
            for decision in self.decisions.values()
            if decision.selected is not None
        )

    @property
    def average_purification_rounds(self) -> float:
        rounds = [
            request_decision.rounds
            for decision in self.decisions.values()
            if decision.selected is not None
            for request_decision in decision.selected.request_decisions
        ]
        return sum(rounds) / len(rounds) if rounds else 0.0


@dataclass
class StageOneIterationRecord:
    iteration: int
    quality_result: QualityAllocationResult
    configuration_result: LinkConfigurationResult
    objective: float
    relative_change: Optional[float]
    configuration_unchanged: bool
    maximum_fidelity_change: Optional[float]
    selected_relaxation: float = 1.0
    minimum_request_capacity: float = 0.0
    total_request_capacity: float = 0.0
    evaluated_relaxation_count: int = 1


@dataclass
class StageOneResult:
    records: List[StageOneIterationRecord]
    quality_prices: Dict[QuantumChannel, float]
    converged: bool
    stop_reason: str

    @property
    def iterations(self) -> int:
        return len(self.records)

    @property
    def final_record(self) -> StageOneIterationRecord:
        if not self.records:
            raise ValueError("stage I did not run any iterations")
        return self.records[-1]

    @property
    def best_record(self) -> StageOneIterationRecord:
        """Return the fairest history-best fully feasible recorded iteration."""
        feasible = [
            record
            for record in self.records
            if record.configuration_result.infeasible_links == 0
        ]
        if not feasible:
            return self.final_record
        return max(
            feasible,
            key=lambda record: (
                record.minimum_request_capacity,
                record.total_request_capacity,
                record.objective,
                -record.configuration_result.average_purification_rounds,
            ),
        )

    @property
    def selected_record(self) -> StageOneIterationRecord:
        """Use the stable final round, or history-best when the limit is reached."""
        return self.final_record if self.converged else self.best_record

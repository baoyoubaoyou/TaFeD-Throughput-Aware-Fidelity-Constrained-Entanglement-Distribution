"""Validated configuration for the collaborative-routing experiments."""

from dataclasses import dataclass, field
from typing import Optional, Tuple


@dataclass(frozen=True)
class WaxmanConfig:
    node_count: int = 100
    size_m: float = 100_000.0
    alpha: float = 0.4
    beta: float = 0.15


@dataclass(frozen=True)
class RequestConfig:
    count: int = 20
    demand_min: int = 50
    demand_max: int = 100
    fidelity_min: float = 0.80
    fidelity_max: float = 0.93
    edr_upper_bound: Optional[float] = None
    allow_node_overlap: bool = True


@dataclass(frozen=True)
class RoutingConfig:
    k: int = 3
    min_hops: int = 3
    max_hops: int = 6
    shortest_hop_quotas: Tuple[Tuple[int, int], ...] = (
        (3, 4),
        (4, 6),
        (5, 8),
        (6, 2),
    )
    max_candidates: int = 1000
    require_k_paths: bool = True


@dataclass(frozen=True)
class LinkConfig:
    fidelity_points: Tuple[float, ...] = (0.80, 0.85, 0.90, 0.95, 0.99)
    base_generation_capacity: float = 20_000.0
    rate_multiplier_min: float = 0.6
    rate_multiplier_max: float = 1.5
    fidelity_scale_min: float = 0.6
    fidelity_scale_max: float = 1.5
    minimum_fidelity: float = 0.80
    maximum_fidelity: float = 0.99

    def raw_rate(self, fidelity: float) -> float:
        """Convert a configuration fidelity to its baseline raw EPR rate.

        The paper's link-configuration model is
        ``R_e(F) = 3/4 * d_e * (1-F)``. This method uses the common baseline
        ``d_0``; the scenario builder obtains the heterogeneous link parameter
        ``d_e = d_0 * xi_e`` by applying the per-link rate multiplier.
        """
        if not self.minimum_fidelity <= fidelity <= 1.0:
            raise ValueError("fidelity is outside the configured physical range")
        return 0.75 * self.base_generation_capacity * (1.0 - fidelity)


@dataclass(frozen=True)
class MemoryConfig:
    capacity_min: int = 80
    capacity_max: int = 120
    rate_per_slot: float = 50.0
    decoherence_rate: float = 0.0
    read_write_delay: float = 0.0


@dataclass(frozen=True)
class PurificationConfig:
    protocol: str = "werner_nested"
    maximum_rounds: int = 6
    before_swapping: bool = True
    failure_consumes_inputs: bool = True


@dataclass(frozen=True)
class SwappingConfig:
    success_probability_min: float = 0.5
    success_probability_max: float = 0.8
    quality_factor: float = 1.0


@dataclass(frozen=True)
class QualityAllocationConfig:
    lambda_0: float = 1.0
    rate_weight: float = 0.4
    memory_weight: float = 0.3
    load_weight: float = 0.2
    quality_weight: float = 0.1
    tolerance: float = 1e-10
    maximum_bisection_iterations: int = 100


@dataclass(frozen=True)
class LinkConfigurationSearchConfig:
    """Search controls for stage I-B's continuous link configuration."""

    coarse_step: float = 0.01
    fine_step: float = 0.001
    retained_coarse_regions: int = 3
    threshold_tolerance: float = 1e-6
    maximum_threshold_iterations: int = 100
    use_precomputed_lookup: bool = True


@dataclass(frozen=True)
class StageOneIterationConfig:
    """Feedback and stopping controls shared by stages I-A and I-B."""

    maximum_iterations: int = 30
    relative_improvement_tolerance: float = 0.05
    price_smoothing: float = 0.2
    normalized_rate_regularization: float = 0.02
    fidelity_update_mode: str = "adaptive"
    fidelity_relaxation: float = 0.2
    adaptive_fidelity_relaxations: Tuple[float, ...] = (1.0, 0.5, 0.25, 0.125)
    adaptive_early_accept: bool = True
    adaptive_acceptance_tolerance: float = 0.01
    active_links_only: bool = True
    infeasible_price_multiplier: float = 2.0
    normalized_rate_floor: float = 1e-9
    stop_when_configuration_unchanged: bool = True


@dataclass(frozen=True)
class ExperimentConfig:
    seed: int = 20260812
    topology: WaxmanConfig = field(default_factory=WaxmanConfig)
    requests: RequestConfig = field(default_factory=RequestConfig)
    routing: RoutingConfig = field(default_factory=RoutingConfig)
    links: LinkConfig = field(default_factory=LinkConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    purification: PurificationConfig = field(default_factory=PurificationConfig)
    swapping: SwappingConfig = field(default_factory=SwappingConfig)
    quality_allocation: QualityAllocationConfig = field(default_factory=QualityAllocationConfig)
    link_configuration_search: LinkConfigurationSearchConfig = field(
        default_factory=LinkConfigurationSearchConfig
    )
    stage_one_iteration: StageOneIterationConfig = field(
        default_factory=StageOneIterationConfig
    )
    metrics: Tuple[str, ...] = (
        "total_edr",
        "minimum_request_edr",
        "request_acceptance_rate",
        "average_purification_rounds",
        "link_utilization",
        "memory_utilization",
    )

    def validate(self) -> None:
        if self.topology.node_count < 2:
            raise ValueError("node_count must be at least 2")
        if not 0 < self.topology.alpha <= 1 or not 0 < self.topology.beta <= 1:
            raise ValueError("Waxman alpha and beta must be in (0, 1]")
        if self.requests.count < 1:
            raise ValueError("request count must be positive")
        if self.requests.demand_min > self.requests.demand_max:
            raise ValueError("invalid request demand range")
        if not 0.25 < self.requests.fidelity_min <= self.requests.fidelity_max <= 1:
            raise ValueError("invalid request fidelity range")
        if self.routing.min_hops > self.routing.max_hops:
            raise ValueError("invalid routing hop range")
        quota_hops = [hop for hop, _ in self.routing.shortest_hop_quotas]
        if len(set(quota_hops)) != len(quota_hops):
            raise ValueError("shortest-hop quotas cannot contain duplicate hop counts")
        if any(
            hop < self.routing.min_hops or hop > self.routing.max_hops or count < 0
            for hop, count in self.routing.shortest_hop_quotas
        ):
            raise ValueError("invalid shortest-hop quota")
        if sum(count for _, count in self.routing.shortest_hop_quotas) != self.requests.count:
            raise ValueError("shortest-hop quotas must sum to the request count")
        if self.memory.capacity_min > self.memory.capacity_max:
            raise ValueError("invalid memory capacity range")
        if self.memory.rate_per_slot <= 0:
            raise ValueError("memory rate per slot must be positive")
        if self.purification.protocol != "werner_nested":
            raise ValueError("only the Werner nested purification model is configured")
        if not 0 < self.swapping.success_probability_min <= self.swapping.success_probability_max <= 1:
            raise ValueError("invalid swapping probability range")
        quality = self.quality_allocation
        weights = (quality.rate_weight, quality.memory_weight, quality.load_weight, quality.quality_weight)
        if quality.lambda_0 <= 0 or any(weight < 0 for weight in weights) or sum(weights) <= 0:
            raise ValueError("invalid initial quality-price parameters")
        if quality.tolerance <= 0 or quality.maximum_bisection_iterations < 1:
            raise ValueError("invalid quality-allocation solver parameters")

        search = self.link_configuration_search
        if search.coarse_step <= 0 or search.fine_step <= 0:
            raise ValueError("configuration-search steps must be positive")
        if search.fine_step > search.coarse_step:
            raise ValueError("fine configuration step cannot exceed the coarse step")
        if search.retained_coarse_regions < 1:
            raise ValueError("at least one coarse search region must be retained")
        if search.threshold_tolerance <= 0 or search.maximum_threshold_iterations < 1:
            raise ValueError("invalid purification-threshold search parameters")

        iteration = self.stage_one_iteration
        if iteration.maximum_iterations < 1:
            raise ValueError("stage-I maximum iterations must be positive")
        if not 0 <= iteration.relative_improvement_tolerance < 1:
            raise ValueError("stage-I relative improvement tolerance must be in [0, 1)")
        if not 0 < iteration.price_smoothing <= 1:
            raise ValueError("price smoothing must be in (0, 1]")
        if iteration.normalized_rate_regularization < 0:
            raise ValueError("normalized rate regularization cannot be negative")
        if iteration.fidelity_update_mode not in {"fixed", "adaptive"}:
            raise ValueError("fidelity update mode must be 'fixed' or 'adaptive'")
        if not 0 < iteration.fidelity_relaxation <= 1:
            raise ValueError("fidelity relaxation must be in (0, 1]")
        if (
            not iteration.adaptive_fidelity_relaxations
            or any(
                not 0 < relaxation <= 1
                for relaxation in iteration.adaptive_fidelity_relaxations
            )
        ):
            raise ValueError("adaptive fidelity relaxations must be in (0, 1]")
        if not 0 <= iteration.adaptive_acceptance_tolerance < 1:
            raise ValueError("adaptive acceptance tolerance must be in [0, 1)")
        if iteration.infeasible_price_multiplier <= 1:
            raise ValueError("infeasible price multiplier must exceed one")
        if iteration.normalized_rate_floor <= 0:
            raise ValueError("normalized rate floor must be positive")

        fidelities = list(self.links.fidelity_points)
        rates = [self.links.raw_rate(fidelity) for fidelity in fidelities]
        if fidelities != sorted(fidelities) or len(set(fidelities)) != len(fidelities):
            raise ValueError("link fidelities must be strictly increasing")
        if fidelities[0] < self.links.minimum_fidelity or fidelities[-1] > self.links.maximum_fidelity:
            raise ValueError("link fidelity points must stay inside the configured range")
        if self.links.base_generation_capacity <= 0:
            raise ValueError("base_generation_capacity must be positive")
        if self.links.rate_multiplier_min > self.links.rate_multiplier_max:
            raise ValueError("invalid link rate multiplier range")
        if self.links.fidelity_scale_min > self.links.fidelity_scale_max:
            raise ValueError("invalid link fidelity scale range")
        if any(rate <= 0 for rate in rates):
            raise ValueError("link rates must be positive")
        if any(rates[i] <= rates[i + 1] for i in range(len(rates) - 1)):
            raise ValueError("raw rates must strictly decrease as fidelity increases")


DEFAULT_CONFIG = ExperimentConfig()

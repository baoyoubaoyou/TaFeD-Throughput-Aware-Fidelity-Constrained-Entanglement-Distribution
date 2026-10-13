"""Pluggable initial quality-price models for stage I-A."""

from typing import Dict, Mapping, Optional, Protocol

from qns.entity.qchannel.qchannel import QuantumChannel
from qns.network.network import QuantumNetwork

from experiments.collaborative_routing.config import QualityAllocationConfig


class QualityPriceModel(Protocol):
    def calculate(
        self,
        network: QuantumNetwork,
        upper_fidelities: Mapping[QuantumChannel, float],
        link_loads: Optional[Mapping[QuantumChannel, float]] = None,
    ) -> Dict[QuantumChannel, float]:
        """Return one strictly positive price for every quantum link."""


class InitialQualityPriceModel:
    """Combine normalized rate, endpoint memory, load, and quality scarcity."""

    def __init__(self, config: QualityAllocationConfig) -> None:
        self.config = config

    @staticmethod
    def _maximum_raw_rate(channel: QuantumChannel) -> float:
        table = getattr(channel, "fidelity_rate_table", None)
        if not table:
            return float(getattr(channel, "raw_entanglement_rate", channel.bandwidth))
        return max(float(point["raw_rate"]) for point in table)

    @staticmethod
    def _endpoint_memory(channel: QuantumChannel) -> float:
        capacities = []
        for node in channel.node_list:
            capacity = sum(memory.capacity for memory in node.memories)
            capacities.append(capacity)
        return float(min(capacities)) if capacities else 0.0

    def calculate(
        self,
        network: QuantumNetwork,
        upper_fidelities: Mapping[QuantumChannel, float],
        link_loads: Optional[Mapping[QuantumChannel, float]] = None,
    ) -> Dict[QuantumChannel, float]:
        link_loads = link_loads or {}
        rates = {channel: self._maximum_raw_rate(channel) for channel in network.qchannels}
        memories = {channel: self._endpoint_memory(channel) for channel in network.qchannels}
        maximum_rate = max(rates.values(), default=1.0)
        maximum_memory = max(memories.values(), default=1.0)
        maximum_load = max(link_loads.values(), default=0.0)
        cfg = self.config
        weight_sum = cfg.rate_weight + cfg.memory_weight + cfg.load_weight + cfg.quality_weight

        prices = {}
        for channel in network.qchannels:
            rate_score = rates[channel] / maximum_rate if maximum_rate > 0 else 0.0
            memory_score = memories[channel] / maximum_memory if maximum_memory > 0 else 0.0
            load_score = link_loads.get(channel, 0.0) / maximum_load if maximum_load > 0 else 0.0
            quality_score = (upper_fidelities[channel] - 0.25) / 0.75
            scarcity = (
                cfg.rate_weight * (1.0 - rate_score)
                + cfg.memory_weight * (1.0 - memory_score)
                + cfg.load_weight * load_score
                + cfg.quality_weight * (1.0 - quality_score)
            ) / weight_sum
            prices[channel] = max(1e-9, cfg.lambda_0 * (1.0 + scarcity))
        return prices

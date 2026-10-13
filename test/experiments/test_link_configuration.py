from experiments.collaborative_routing.config import LinkConfig, LinkConfigurationSearchConfig
from experiments.collaborative_routing.link_configuration import (
    evaluate_link_configuration,
    purification_memory_slots,
    search_link_configuration,
)
from qns.entity.memory.memory import QuantumMemory
from qns.entity.node.node import QNode
from qns.entity.qchannel.qchannel import QuantumChannel
from qns.network.requests import Request


def _link_with_memory(capacity=80):
    left, right = QNode("left"), QNode("right")
    channel = QuantumChannel("link")
    left.add_qchannel(channel)
    right.add_qchannel(channel)
    left.add_memory(QuantumMemory("ml", capacity=capacity))
    right.add_memory(QuantumMemory("mr", capacity=capacity))
    channel.generation_capacity = 20_000.0
    return left, right, channel


def test_effective_rate_includes_purification_failures():
    left, right, channel = _link_with_memory()
    request = Request(left, right, {"demand_intensity": 100})
    evaluation = evaluate_link_configuration(channel, [(request, 0.95)], 0.90, 6)

    assert evaluation.feasible
    assert evaluation.request_decisions[0].rounds > 0
    assert evaluation.average_raw_pairs > 2
    assert evaluation.effective_rate < evaluation.raw_rate / 2


def test_configuration_search_returns_a_point_at_requested_precision():
    left, right, channel = _link_with_memory()
    request = Request(left, right, {"demand_intensity": 100})
    decision = search_link_configuration(
        channel,
        [(request, 0.96)],
        LinkConfig(),
        LinkConfigurationSearchConfig(),
        6,
    )

    assert decision.feasible
    assert decision.selected is not None
    assert abs(decision.selected.fidelity * 1000 - round(decision.selected.fidelity * 1000)) < 1e-9
    assert decision.selected.request_decisions[0].output_fidelity >= 0.96
    assert purification_memory_slots(decision.selected.request_decisions[0].rounds) <= 80

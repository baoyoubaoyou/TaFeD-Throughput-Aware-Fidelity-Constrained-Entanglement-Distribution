import math

from experiments.collaborative_routing.config import LinkConfig
from experiments.collaborative_routing.purification_lookup import (
    build_werner_purification_lookup,
)
from experiments.collaborative_routing.quality_allocation import werner_parameter
from experiments.collaborative_routing.spfd import (
    SPFDLinkDemand,
    evaluate_spfd_greedy_candidate,
    select_spfd_link_configuration,
    spfd_equal_link_fidelity,
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


def test_equal_split_reconstructs_the_end_to_end_werner_requirement():
    request_fidelity = 0.91
    hop_count = 5
    link_fidelity = spfd_equal_link_fidelity(request_fidelity, hop_count)

    reconstructed = werner_parameter(link_fidelity) ** hop_count

    assert abs(reconstructed - werner_parameter(request_fidelity)) < 1e-12


def test_greedy_candidate_includes_purification_failures_in_consumption():
    left, right, channel = _link_with_memory()
    request = Request(left, right, {"demand_intensity": 100})
    required = 0.96
    demand = SPFDLinkDemand(
        request=request,
        required_fidelity=required,
        required_log_werner=math.log(werner_parameter(required)),
        demand_rate=100.0,
    )
    point = build_werner_purification_lookup(0.80, 0.99, 0.001, 6)[100]

    evaluation = evaluate_spfd_greedy_candidate(channel, [demand], point)

    assert evaluation.feasible
    assert evaluation.allocations[0].rounds > 0
    assert evaluation.allocations[0].expected_raw_pairs > 2.0
    assert evaluation.allocations[0].raw_rate_consumed == (
        evaluation.allocations[0].served_rate
        * evaluation.allocations[0].expected_raw_pairs
    )


def test_link_selection_maximizes_the_original_spfd_greedy_objective():
    left, right, channel = _link_with_memory()
    requests = [
        Request(left, right, {"demand_intensity": 80}),
        Request(left, right, {"demand_intensity": 100}),
    ]
    requirements = (0.92, 0.96)
    demands = [
        SPFDLinkDemand(
            request=request,
            required_fidelity=required,
            required_log_werner=math.log(werner_parameter(required)),
            demand_rate=float(request.attr["demand_intensity"]),
        )
        for request, required in zip(requests, requirements)
    ]
    config = LinkConfig()
    lookup = build_werner_purification_lookup(
        config.minimum_fidelity,
        config.maximum_fidelity,
        0.001,
        6,
    )

    decision = select_spfd_link_configuration(channel, demands, lookup)

    assert decision.feasible
    assert decision.selected is not None
    assert decision.selected.total_served_rate == max(
        item.total_served_rate for item in decision.candidates if item.feasible
    )

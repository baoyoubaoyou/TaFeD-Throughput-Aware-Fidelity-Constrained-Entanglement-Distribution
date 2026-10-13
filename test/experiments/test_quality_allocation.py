from experiments.collaborative_routing.quality_allocation import (
    allocate_request_quality,
    solve_path_fidelity_allocation,
)
from experiments.collaborative_routing.quality_models import LinkQualityState
from qns.entity.node.node import QNode
from qns.entity.qchannel.qchannel import QuantumChannel
from qns.network.requests import Request


def _connect(node_a, node_b, name):
    channel = QuantumChannel(name=name)
    node_a.add_qchannel(channel)
    node_b.add_qchannel(channel)
    return channel


def test_equal_prices_produce_equal_fidelity_requirements():
    nodes = [QNode(f"n{i}") for i in range(4)]
    channels = [_connect(nodes[i], nodes[i + 1], f"e{i}") for i in range(3)]
    states = {
        channel: LinkQualityState(channel, 0.80, 0.999, 1.0)
        for channel in channels
    }

    plan = solve_path_fidelity_allocation(nodes, 0.90, states)
    values = list(plan.fidelity_requirements.values())

    assert plan.feasible
    assert max(values) - min(values) < 1e-12
    assert plan.achieved_fidelity >= 0.90
    assert plan.iterations <= 100


def test_expensive_link_receives_a_lower_requirement():
    nodes = [QNode(f"n{i}") for i in range(4)]
    channels = [_connect(nodes[i], nodes[i + 1], f"e{i}") for i in range(3)]
    prices = [1.0, 2.0, 1.0]
    states = {
        channel: LinkQualityState(channel, 0.80, 0.999, price)
        for channel, price in zip(channels, prices)
    }

    plan = solve_path_fidelity_allocation(nodes, 0.85, states)

    assert plan.feasible
    assert plan.fidelity_requirements[channels[1]] < plan.fidelity_requirements[channels[0]]
    assert plan.fidelity_requirements[channels[1]] < plan.fidelity_requirements[channels[2]]


def test_path_is_rejected_when_its_upper_envelope_is_too_low():
    nodes = [QNode(f"n{i}") for i in range(4)]
    channels = [_connect(nodes[i], nodes[i + 1], f"e{i}") for i in range(3)]
    states = {
        channel: LinkQualityState(channel, 0.80, 0.90, 1.0)
        for channel in channels
    }

    plan = solve_path_fidelity_allocation(nodes, 0.93, states)

    assert not plan.feasible
    assert plan.status == "quality_infeasible"


def test_request_keeps_candidates_and_selects_lowest_cost_path():
    source, a, b, c, d, destination = [QNode(name) for name in "SABCDT"]
    path_1 = [source, a, b, destination]
    path_2 = [source, c, d, destination]
    channels_1 = [_connect(path_1[i], path_1[i + 1], f"p1-{i}") for i in range(3)]
    channels_2 = [_connect(path_2[i], path_2[i + 1], f"p2-{i}") for i in range(3)]
    states = {
        **{channel: LinkQualityState(channel, 0.80, 0.999, 2.0) for channel in channels_1},
        **{channel: LinkQualityState(channel, 0.80, 0.999, 1.0) for channel in channels_2},
    }
    candidate_routes = [
        (3.0, path_1[1], path_1),
        (3.0, path_2[1], path_2),
    ]
    request = Request(
        source,
        destination,
        {"required_fidelity": 0.85, "candidate_routes": candidate_routes},
    )

    result = allocate_request_quality(request, states)

    assert result.selected_candidate_index == 1
    assert request.attr["selected_route"] == candidate_routes[1]
    assert request.attr["backup_routes"] == [candidate_routes[0]]
    assert request.attr["quality_status"] == "selected"
    assert len(request.attr["candidate_routes"]) == 2

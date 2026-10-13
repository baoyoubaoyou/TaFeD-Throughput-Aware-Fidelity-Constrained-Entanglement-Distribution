from experiments.collaborative_routing.swapping_tree import (
    build_fixed_request_swapping_tree,
    optimize_request_swapping_tree,
)
from qns.entity.node.node import QNode
from qns.entity.qchannel.qchannel import QuantumChannel
from qns.network.requests import Request


def _connect(left, right, name):
    channel = QuantumChannel(name)
    left.add_qchannel(channel)
    right.add_qchannel(channel)
    return channel


def test_interval_dp_chooses_tree_that_protects_expensive_link():
    nodes = [QNode(f"n{i}") for i in range(4)]
    channels = [_connect(nodes[i], nodes[i + 1], f"e{i}") for i in range(3)]
    nodes[1].swap_success_probability = 0.5
    nodes[2].swap_success_probability = 0.5
    request = Request(nodes[0], nodes[-1], {"demand_intensity": 100.0})

    tree = optimize_request_swapping_tree(
        request,
        nodes,
        channels,
        purification_costs={channels[0]: 10.0, channels[1]: 1.0, channels[2]: 1.0},
        link_prices={channel: 1.0 for channel in channels},
    )

    assert tree.root.split_index == 1
    assert tree.amplification_factors[channels[0]] == 2.0
    assert tree.amplification_factors[channels[1]] == 4.0
    assert tree.amplification_factors[channels[2]] == 4.0


def test_tree_cost_equals_sum_of_weighted_leaf_raw_costs():
    nodes = [QNode(f"n{i}") for i in range(5)]
    channels = [_connect(nodes[i], nodes[i + 1], f"e{i}") for i in range(4)]
    for index, node in enumerate(nodes[1:-1], start=1):
        node.swap_success_probability = 0.5 + 0.1 * index
    request = Request(nodes[0], nodes[-1], {"demand_intensity": 100.0})
    eta = {channel: float(index + 1) for index, channel in enumerate(channels)}
    prices = {channel: 1.0 + index for index, channel in enumerate(channels)}

    tree = optimize_request_swapping_tree(
        request,
        nodes,
        channels,
        purification_costs=eta,
        link_prices=prices,
    )

    reconstructed = sum(
        prices[channel] * tree.raw_costs[channel] for channel in channels
    )
    assert abs(tree.weighted_cost - reconstructed) < 1e-10


def test_optimal_tree_never_costs_more_than_left_deep_tree():
    nodes = [QNode(f"n{i}") for i in range(7)]
    channels = [_connect(nodes[i], nodes[i + 1], f"e{i}") for i in range(6)]
    for index, node in enumerate(nodes[1:-1], start=1):
        node.swap_success_probability = 0.50 + 0.05 * index
    request = Request(nodes[0], nodes[-1], {"demand_intensity": 100.0})
    eta = {channel: float(index + 1) for index, channel in enumerate(channels)}
    prices = {channel: 1.0 + 0.2 * index for index, channel in enumerate(channels)}

    fixed = build_fixed_request_swapping_tree(
        request, nodes, channels, eta, prices
    )
    optimal = optimize_request_swapping_tree(
        request, nodes, channels, eta, prices
    )

    assert optimal.weighted_cost <= fixed.weighted_cost

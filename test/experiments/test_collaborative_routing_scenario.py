from dataclasses import replace

from experiments.collaborative_routing.config import DEFAULT_CONFIG
from experiments.collaborative_routing.scenario import build_scenario


def test_link_rate_conversion_formula():
    links = DEFAULT_CONFIG.links
    assert abs(links.raw_rate(0.80) - 3000.0) < 1e-9
    assert abs(links.raw_rate(0.99) - 150.0) < 1e-9


def test_small_collaborative_routing_scenario():
    config = replace(
        DEFAULT_CONFIG,
        seed=7,
        topology=replace(DEFAULT_CONFIG.topology, node_count=30, alpha=0.7, beta=0.3),
        requests=replace(DEFAULT_CONFIG.requests, count=4),
        routing=replace(DEFAULT_CONFIG.routing, shortest_hop_quotas=((3, 4),)),
    )
    scenario = build_scenario(config)

    assert len(scenario.network.nodes) == 30
    assert len(scenario.requests) == 4
    assert all(80 <= node.memories[0].capacity <= 120 for node in scenario.network.nodes)
    assert all(0.5 <= node.swap_success_probability <= 0.8 for node in scenario.network.nodes)

    for channel in scenario.network.qchannels:
        assert len(channel.fidelity_rate_table) == 5
        fidelities = [point["fidelity"] for point in channel.fidelity_rate_table]
        rates = [point["raw_rate"] for point in channel.fidelity_rate_table]
        assert fidelities == sorted(fidelities)
        assert rates == sorted(rates, reverse=True)
        for point in channel.fidelity_rate_table:
            expected = 0.75 * channel.generation_capacity * (1.0 - point["fidelity"])
            assert abs(point["raw_rate"] - expected) < 1e-9

    for request in scenario.requests:
        assert 50 <= request.attr["demand_intensity"] <= 100
        assert 0.80 <= request.attr["required_fidelity"] <= 0.93
        assert len(request.attr["candidate_routes"]) == 3
        assert request.attr["shortest_path_hops"] == 3
        assert all(3 <= len(route[2]) - 1 <= 6 for route in request.attr["candidate_routes"])

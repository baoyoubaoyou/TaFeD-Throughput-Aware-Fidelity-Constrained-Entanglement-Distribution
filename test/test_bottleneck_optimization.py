from dataclasses import replace

from experiments.collaborative_routing import (
    BottleneckOptimizationConfig,
    DEFAULT_CONFIG,
    build_scenario,
    run_bottleneck_optimized_stage_one,
)


def _config():
    request_count = 10
    return replace(
        DEFAULT_CONFIG,
        seed=20260812,
        requests=replace(DEFAULT_CONFIG.requests, count=request_count),
        routing=replace(
            DEFAULT_CONFIG.routing,
            shortest_hop_quotas=((3, 3), (4, 3), (5, 2), (6, 2)),
        ),
    )


def test_bottleneck_refinement_preserves_history_best_minimum_edr():
    result = run_bottleneck_optimized_stage_one(
        build_scenario(_config()),
        BottleneckOptimizationConfig(maximum_refinement_iterations=2),
        mutate_requests=False,
    )
    base = result.records[0].throughput_result.minimum_request_edr
    selected = result.selected_record.throughput_result.minimum_request_edr
    assert selected + 1e-9 >= base
    assert all(price > 0 for price in result.records[-1].quality_prices.values())
    assert set(result.records[-1].bottleneck_channels).issubset(
        result.records[-1].throughput_result.link_allocations
    )

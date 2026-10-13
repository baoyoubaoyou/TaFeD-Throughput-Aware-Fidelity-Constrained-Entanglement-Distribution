from experiments.collaborative_routing import (
    MarginalThroughputConfig,
    build_scenario,
    run_marginal_throughput_optimized_stage_one,
)
from examples.request_scaling_tree_comparison import experiment_config


def test_accepted_marginal_price_updates_do_not_reduce_total_edr():
    result = run_marginal_throughput_optimized_stage_one(
        build_scenario(experiment_config(10, 20260812)),
        MarginalThroughputConfig(maximum_iterations=3),
        mutate_requests=False,
    )
    accepted = [record for record in result.records if record.accepted]
    totals = [record.throughput_result.total_edr for record in accepted]
    assert totals
    assert all(current + 1e-9 >= previous for previous, current in zip(totals, totals[1:]))
    assert all(price > 0 for price in result.records[-1].marginal_prices.values())


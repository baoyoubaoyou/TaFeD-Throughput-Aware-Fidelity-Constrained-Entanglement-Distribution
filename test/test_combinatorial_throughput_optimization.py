from experiments.collaborative_routing import (
    CombinatorialThroughputConfig,
    build_scenario,
    run_combinatorial_throughput_optimized_stage_one,
)
from examples.request_scaling_tree_comparison import experiment_config


def test_combinatorial_search_dominates_both_initial_total_edrs():
    result = run_combinatorial_throughput_optimized_stage_one(
        build_scenario(experiment_config(10, 20260812)),
        CombinatorialThroughputConfig(maximum_iterations=2),
        mutate_requests=False,
    )
    totals = [
        record.throughput_result.total_edr
        for record in result.records if record.accepted
    ]
    assert totals[0] + 1e-9 >= max(
        result.joint_initial_total_edr, result.spfd_initial_total_edr
    )
    assert all(current > previous for previous, current in zip(totals, totals[1:]))


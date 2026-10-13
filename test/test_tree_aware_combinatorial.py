from experiments.collaborative_routing import (
    CombinatorialThroughputConfig,
    build_scenario,
    run_tree_aware_combinatorial_throughput,
)
from examples.request_scaling_tree_comparison import experiment_config


def test_tree_aware_result_dominates_both_optimized_initializations():
    result = run_tree_aware_combinatorial_throughput(
        build_scenario(experiment_config(10, 20260812)),
        CombinatorialThroughputConfig(maximum_iterations=2),
        mutate_requests=False,
    )
    assert result.selected_record.throughput_result.total_edr + 1e-9 >= max(
        result.joint_initial_total_edr,
        result.spfd_initial_total_edr,
    )


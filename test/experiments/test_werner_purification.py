from experiments.collaborative_routing.purification import minimum_plan, output_fidelity, success_probability
from experiments.collaborative_routing.purification_lookup import (
    build_werner_purification_lookup,
    find_minimum_lookup_plan,
)


def test_werner_round_equations():
    probability = success_probability(0.92)
    fidelity = output_fidelity(0.92)
    assert 0 < probability <= 1
    assert abs(fidelity - 0.9422582558829347) < 1e-12


def test_minimum_plan_and_infeasible_target():
    plan = minimum_plan(0.92, 0.985, maximum_rounds=6)
    assert plan is not None
    assert plan.rounds == 5
    assert plan.output_fidelity >= 0.985
    assert plan.expected_raw_pairs > 1

    assert minimum_plan(0.82, 0.9999, maximum_rounds=2) is None


def test_cached_lookup_matches_direct_werner_calculation():
    first = build_werner_purification_lookup(0.80, 0.99, 0.005, 6)
    second = build_werner_purification_lookup(0.80, 0.99, 0.005, 6)

    assert first is second
    assert len(first) == 39
    point = next(point for point in first if abs(point.fidelity - 0.92) < 1e-12)
    lookup_plan = find_minimum_lookup_plan(point, 0.985)
    direct_plan = minimum_plan(0.92, 0.985, 6)
    assert lookup_plan is not None and direct_plan is not None
    assert lookup_plan.rounds == direct_plan.rounds
    assert abs(lookup_plan.output_fidelity - direct_plan.output_fidelity) < 1e-12
    assert abs(lookup_plan.expected_raw_pairs - direct_plan.expected_raw_pairs) < 1e-12

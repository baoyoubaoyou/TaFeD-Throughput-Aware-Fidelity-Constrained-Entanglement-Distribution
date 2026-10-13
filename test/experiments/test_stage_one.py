from experiments.collaborative_routing.quality_allocation import solve_path_fidelity_allocation
from experiments.collaborative_routing.quality_models import (
    LinkQualityState,
    QualityAllocationResult,
    RequestQualityPlan,
)
from experiments.collaborative_routing.stage_one import damp_quality_requirements
from experiments.collaborative_routing.variants import (
    adaptive_damping_config,
    fixed_damping_config,
)
from experiments.collaborative_routing.config import DEFAULT_CONFIG
from qns.entity.node.node import QNode
from qns.entity.qchannel.qchannel import QuantumChannel
from qns.network.requests import Request


def _connect(left, right, name):
    channel = QuantumChannel(name)
    left.add_qchannel(channel)
    right.add_qchannel(channel)
    return channel


def test_fidelity_damping_is_a_feasible_convex_combination():
    nodes = [QNode(f"n{i}") for i in range(4)]
    channels = [_connect(nodes[i], nodes[i + 1], f"e{i}") for i in range(3)]
    states = {
        channel: LinkQualityState(channel, 0.80, 0.999, 1.0)
        for channel in channels
    }
    request = Request(nodes[0], nodes[-1], {
        "required_fidelity": 0.85,
        "candidate_routes": [(3.0, nodes[1], nodes)],
    })
    plan = solve_path_fidelity_allocation(nodes, 0.85, states)
    request_plan = RequestQualityPlan(request, [plan], plan.candidate_index)
    result = QualityAllocationResult(states, [request_plan])
    original = dict(plan.fidelity_requirements)
    previous = {
        (id(request), channel): original[channel] + 0.01
        for channel in channels
    }

    damp_quality_requirements(result, previous, relaxation=0.2)

    relaxed_plan = result.request_plans[0].selected_plan
    assert relaxed_plan is not None
    for channel in channels:
        expected = 0.8 * previous[(id(request), channel)] + 0.2 * original[channel]
        assert abs(relaxed_plan.fidelity_requirements[channel] - expected) < 1e-12
    assert relaxed_plan.achieved_fidelity >= request.attr["required_fidelity"]
    assert relaxed_plan.status == "allocated_relaxed"


def test_fixed_and_adaptive_variants_remain_independently_selectable():
    fixed = fixed_damping_config(DEFAULT_CONFIG)
    adaptive = adaptive_damping_config(DEFAULT_CONFIG)

    assert fixed.stage_one_iteration.fidelity_update_mode == "fixed"
    assert fixed.stage_one_iteration.fidelity_relaxation == 0.2
    assert adaptive.stage_one_iteration.fidelity_update_mode == "adaptive"
    assert adaptive.stage_one_iteration.adaptive_fidelity_relaxations == (
        1.0,
        0.5,
        0.25,
        0.125,
    )
    assert adaptive.link_configuration_search.fine_step == 0.001
    assert adaptive.link_configuration_search.use_precomputed_lookup
    assert adaptive.stage_one_iteration.active_links_only
    assert adaptive.stage_one_iteration.adaptive_early_accept
    fixed.validate()
    adaptive.validate()

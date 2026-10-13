from experiments.collaborative_routing.configuration_models import (
    LinkConfigurationDecision,
    LinkConfigurationEvaluation,
    LinkConfigurationResult,
    RequestPurificationDecision,
)
from experiments.collaborative_routing.quality_models import (
    CandidatePathQualityPlan,
    QualityAllocationResult,
    RequestQualityPlan,
)
from experiments.collaborative_routing.throughput_allocation import (
    progressive_fill_end_to_end_throughput,
)
from qns.entity.node.node import QNode
from qns.entity.qchannel.qchannel import QuantumChannel
from qns.network.requests import Request


def _connect(left, right, name):
    channel = QuantumChannel(name)
    left.add_qchannel(channel)
    right.add_qchannel(channel)
    return channel


def _quality_result(requests, path, channels):
    plans = []
    for request in requests:
        plan = CandidatePathQualityPlan(
            candidate_index=0,
            path=path,
            channels=channels,
            feasible=True,
            status="test",
            quality_budget=0.0,
            fidelity_requirements={channel: 0.9 for channel in channels},
        )
        plans.append(RequestQualityPlan(request, [plan], 0))
    return QualityAllocationResult({}, plans)


def _configuration_result(channel, requests, raw_rate, expected_raw_pairs=1.0):
    request_decisions = [
        RequestPurificationDecision(
            request=request,
            required_fidelity=0.9,
            demand_weight=1.0 / len(requests),
            rounds=0,
            output_fidelity=0.9,
            expected_raw_pairs=expected_raw_pairs,
            memory_slots_per_endpoint=1,
        )
        for request in requests
    ]
    evaluation = LinkConfigurationEvaluation(
        channel=channel,
        fidelity=0.9,
        feasible=True,
        raw_rate=raw_rate,
        effective_rate=raw_rate / expected_raw_pairs,
        average_raw_pairs=expected_raw_pairs,
        request_decisions=request_decisions,
    )
    return LinkConfigurationResult({
        channel: LinkConfigurationDecision(channel, evaluation, 1, 1),
    })


def test_progressive_filling_splits_one_bottleneck_equally():
    left, right = QNode("left"), QNode("right")
    channel = _connect(left, right, "e")
    requests = [
        Request(left, right, {"demand_intensity": 100.0}),
        Request(left, right, {"demand_intensity": 100.0}),
    ]
    result = progressive_fill_end_to_end_throughput(
        _quality_result(requests, [left, right], [channel]),
        _configuration_result(channel, requests, raw_rate=100.0),
    )

    rates = [result.request_allocations[id(request)].allocated_rate for request in requests]
    assert rates == [50.0, 50.0]
    assert result.total_edr == 100.0
    assert result.maximum_link_utilization == 1.0


def test_purification_cost_reduces_delivered_rate():
    left, right = QNode("left"), QNode("right")
    channel = _connect(left, right, "e")
    request = Request(left, right, {"demand_intensity": 100.0})
    result = progressive_fill_end_to_end_throughput(
        _quality_result([request], [left, right], [channel]),
        _configuration_result(
            channel,
            [request],
            raw_rate=100.0,
            expected_raw_pairs=2.5,
        ),
    )

    assert result.request_allocations[id(request)].allocated_rate == 40.0


def test_swap_failure_consumes_all_path_links_in_expectation():
    source, middle, destination = QNode("s"), QNode("m"), QNode("d")
    first = _connect(source, middle, "e1")
    second = _connect(middle, destination, "e2")
    middle.swap_success_probability = 0.5
    request = Request(source, destination, {"demand_intensity": 100.0})
    quality = _quality_result(
        [request],
        [source, middle, destination],
        [first, second],
    )
    first_result = _configuration_result(first, [request], raw_rate=100.0)
    second_result = _configuration_result(second, [request], raw_rate=100.0)
    configuration = LinkConfigurationResult({
        **first_result.decisions,
        **second_result.decisions,
    })

    result = progressive_fill_end_to_end_throughput(quality, configuration)

    allocation = result.request_allocations[id(request)]
    assert allocation.swap_success_probability == 0.5
    assert allocation.allocated_rate == 50.0
    assert all(
        link.raw_consumed == 100.0 for link in result.link_allocations.values()
    )

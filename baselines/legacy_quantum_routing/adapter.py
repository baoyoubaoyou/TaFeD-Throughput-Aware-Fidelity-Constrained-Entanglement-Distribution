"""Adapters from the current Scenario/Request objects to legacy algorithms."""

from __future__ import annotations

import importlib
import math
import sys
import time
from dataclasses import replace
import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from .runtime import LegacyRuntimeConfig


ORIGINAL_DIR = Path(__file__).with_name("original")
BOUNDED_DIR = Path(__file__).with_name("bounded")


@dataclass
class BaselineResult:
    algorithm: str
    selected_paths: List[Any] = field(default_factory=list)
    per_request_throughput: List[float] = field(default_factory=list)
    total_throughput: float = 0.0
    accepted_requests: int = 0
    runtime_seconds: float = 0.0
    status: str = "completed"
    metadata: Dict[str, Any] = field(default_factory=dict)


def _load_original(name: str, bounded: bool = False):
    # The legacy routing modules import two unused SciPy combinatorics helpers.
    # Supply a tiny compatibility module when SciPy is absent, without editing
    # the preserved source snapshot.
    try:
        importlib.import_module("scipy.special")
    except ModuleNotFoundError:
        special = types.ModuleType("scipy.special")
        special.comb = math.comb
        special.perm = math.perm
        scipy = types.ModuleType("scipy")
        scipy.special = special
        sys.modules.setdefault("scipy", scipy)
        sys.modules.setdefault("scipy.special", special)
    source_dir = BOUNDED_DIR if bounded else ORIGINAL_DIR
    source = str(source_dir)
    if source not in sys.path:
        sys.path.insert(0, source)
    if bounded:
        original = str(ORIGINAL_DIR)
        if original not in sys.path:
            sys.path.insert(1, original)
    return importlib.import_module(name)


def _legacy_graph(scenario):
    """Build the legacy directed adjacency matrix from one Scenario.

    The graph is rebuilt for each baseline, so legacy in-place resource updates
    cannot leak into another algorithm.
    """
    vlink = _load_original("vlink")
    nodes = [node.name for node in scenario.network.nodes]
    index = {name: i for i, name in enumerate(nodes)}
    edges = []
    seen = set()
    for channel in scenario.network.qchannels:
        if len(channel.node_list) != 2:
            continue
        left, right = (channel.node_list[0].name, channel.node_list[1].name)
        key = tuple(sorted((left, right)))
        if key in seen:
            continue
        seen.add(key)
        # The legacy search uses `_c` both as a discrete purification-table
        # depth and as a rate budget.  Feeding a real 800--1200 pairs/s rate
        # into that table makes it grow linearly and is computationally
        # meaningless.  Keep its decision-stage feasibility in memory-slot
        # units; the shared real-rate model is applied by the common evaluator.
        capacity = int(max(0, min(
            getattr(channel, "memory_capacity", 0),
            getattr(channel, "generation_capacity", 0),
        )))
        fidelity = float(getattr(channel, "fidelity", 0.0))
        for source, target in ((left, right), (right, left)):
            edge = vlink.Link(source, target, capacity, fidelity, 1.0, True)
            edge.calftable()
            edges.append(edge)
    graph = [[vlink.Link() for _ in nodes] for _ in nodes]
    for edge in edges:
        graph[index[edge.fr]][index[edge.to]] = edge
    return graph


def _request_vectors(requests: Sequence[Any]) -> Tuple[List[List[int]], List[float], List[float]]:
    sdset, fthset, reqset = [], [], []
    for request in requests:
        attr = request.attr
        sdset.append([request.src.name, request.dest.name])
        fthset.append(float(attr.get("required_fidelity", 0.8)))
        reqset.append(float(attr.get("demand_intensity", 0.0)))
    return sdset, fthset, reqset


def _normalise_paths(paths, node_names):
    return [[node_names[i] for i in path] for path_group in paths for path in path_group]


def run_baseline(scenario, algorithm: str, runtime: LegacyRuntimeConfig | None = None) -> BaselineResult:
    """Run one legacy multi-request baseline on an isolated resource graph."""
    runtime = runtime or LegacyRuntimeConfig()
    runtime.validate()
    if algorithm not in {"QPath", "QLeap", "SFTrap"}:
        raise ValueError(f"unknown baseline algorithm: {algorithm}")

    if algorithm == "SFTrap":
        from .sftrap_compatible import run_sftrap
        # SFTrap's adaptive cancellation operates on a wider route pool than
        # the two legacy single-path baselines; retain the current candidate
        # ordering while exposing two additional alternatives.
        sftrap_runtime = replace(
            runtime,
            max_candidate_paths=max(10, runtime.max_candidate_paths),
        )
        return run_sftrap(scenario, sftrap_runtime)

    if runtime.mode == "reimplemented":
        from .paper_reimplemented import run_reimplemented
        return run_reimplemented(scenario, algorithm, runtime)

    started = time.perf_counter()
    graph = _legacy_graph(scenario)
    node_names = [node.name for node in scenario.network.nodes]
    name_to_index = {name: i for i, name in enumerate(node_names)}
    sdset, fthset, reqset = _request_vectors(scenario.requests)
    sdset = [[name_to_index[src], name_to_index[dst]] for src, dst in sdset]

    # The original entry points use this argument for both path discovery and
    # global reallocation. Five rounds is enough for bounded smoke tests but
    # truncates the legacy candidate search in adapted comparisons. Give the
    # search a moderate budget while keeping it finite.
    if runtime.mode == "adapted":
        # The legacy source applies this bound to the whole request batch, not
        # per request. Scale it with the batch size so a 40-request experiment
        # is not accidentally truncated after only a handful of selections.
        search_rounds = min(20, max(
            runtime.max_reallocation_rounds,
            len(scenario.requests) * runtime.max_candidate_paths * 2,
            20,
        ))
    else:
        search_rounds = runtime.max_reallocation_rounds
    if algorithm == "QPath":
        module = _load_original("mqpath", bounded=runtime.mode in {"bounded", "adapted"})
        runner = module.MQpath()
        kwargs = {}
        if runtime.mode in {"bounded", "adapted"}:
            kwargs = {
                "max_reallocation_rounds": search_rounds,
                "max_candidate_paths": runtime.max_candidate_paths,
            }
        raw = runner.alg4(graph, sdset, fthset, reqset, **kwargs)
    else:
        module = _load_original("mqleap", bounded=runtime.mode in {"bounded", "adapted"})
        runner = module.MQleap()
        kwargs = {}
        if runtime.mode in {"bounded", "adapted"}:
            kwargs = {
                "max_reallocation_rounds": search_rounds,
                "max_candidate_paths": runtime.max_candidate_paths,
            }
        raw = runner.alg3(graph, sdset, fthset, reqset, **kwargs)

    paths, throughputs, fidelities, rounds, consumptions, total = raw
    from .evaluation import evaluate_legacy_routes

    named_path_groups = [
        [[node_names[index] for index in path] for path in request_paths]
        for request_paths in paths
    ]
    if runtime.mode == "adapted":
        # Preserve legacy routes, then perform a bounded physical repair. The
        # legacy algorithms can return no route for a request, or routes that
        # are valid in their discrete model but very expensive under the
        # current Werner/memory model. Add current-model alternatives and keep
        # the shortest feasible-looking routes in the candidate pool. The
        # legacy decision remains represented in the pool and is still used as
        # the first tie-breaker.
        for request_index, request in enumerate(scenario.requests):
            legacy_paths = list(named_path_groups[request_index])
            existing = {tuple(item) for item in legacy_paths}
            for route in request.attr.get("candidate_routes", []):
                candidate = [node.name for node in route[2]]
                key = tuple(candidate)
                if key not in existing:
                    named_path_groups[request_index].append(candidate)
                    existing.add(key)
            legacy_rank = {tuple(path): index for index, path in enumerate(legacy_paths)}
            named_path_groups[request_index].sort(
                key=lambda path: (
                    len(path),
                    0 if tuple(path) in legacy_rank else 1,
                    legacy_rank.get(tuple(path), runtime.max_candidate_paths),
                )
            )
            named_path_groups[request_index] = named_path_groups[request_index][:max(runtime.max_candidate_paths, 5)]
        rounds = [
            [item for item in request_rounds[:len(named_path_groups[index])]]
            for index, request_rounds in enumerate(rounds)
        ]
    per_request, evaluated_candidates, evaluation_iterations = evaluate_legacy_routes(
        scenario, named_path_groups, rounds, weighted=runtime.mode == "adapted"
    )
    elapsed = time.perf_counter() - started
    return BaselineResult(
        algorithm=algorithm,
        selected_paths=_normalise_paths(paths, node_names),
        per_request_throughput=per_request,
        total_throughput=sum(per_request),
        accepted_requests=sum(value > 0 for value in per_request),
        runtime_seconds=elapsed,
        metadata={
            "legacy_fidelities": fidelities,
            "purification_rounds": rounds,
            "legacy_consumptions": consumptions,
            "legacy_total_throughput": float(total),
            "physical_evaluation_iterations": evaluation_iterations,
            "physically_feasible_paths": len(evaluated_candidates),
            "adaptation": runtime.mode == "adapted",
        },
    )

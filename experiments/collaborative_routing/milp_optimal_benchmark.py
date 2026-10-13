"""Small-scenario MILP benchmark for fixed-path joint optimization.

The MILP is a column-selection model.  Each column is one complete request
plan: per-link base configuration, per-link purification depth, and one
ordered swapping tree.  Nonlinear quantum formulas are evaluated before model
construction; Gurobi only sees binary choices and linear capacity constraints.
"""

from dataclasses import dataclass, field
from itertools import product
import math
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from qns.entity.node.node import QNode
from qns.entity.qchannel.qchannel import QuantumChannel
from qns.network.requests import Request

from experiments.collaborative_routing.config import ExperimentConfig
from experiments.collaborative_routing.link_configuration import (
    memory_limited_raw_rate,
    raw_entanglement_rate,
)
from experiments.collaborative_routing.purification_lookup import (
    build_werner_purification_lookup,
)
from experiments.collaborative_routing.purification import (
    fidelity_after_rounds,
    minimum_plan,
)
from experiments.collaborative_routing.quality_allocation import werner_parameter


@dataclass(frozen=True)
class MILPBenchmarkConfig:
    """Controls the finite candidate space solved by the MILP."""

    path_candidate_indices: Optional[Tuple[int, ...]] = None
    maximum_purification_rounds: int = 4
    link_option_limit: Optional[int] = 8
    mip_gap: float = 1e-6
    time_limit_seconds: Optional[float] = 300.0
    verbose: bool = True


@dataclass(frozen=True)
class LinkOption:
    channel: QuantumChannel
    config_fidelity: float
    output_fidelity: float
    rounds: int
    expected_raw_pairs: float
    raw_rate: float
    memory_slots_per_endpoint: int


@dataclass(frozen=True)
class TreeShape:
    """An ordered binary tree over a path interval [left, right)."""

    left: int
    right: int
    split: Optional[int] = None
    left_child: Optional["TreeShape"] = None
    right_child: Optional["TreeShape"] = None

    @property
    def is_leaf(self) -> bool:
        return self.right == self.left + 1

    @property
    def signature(self):
        if self.is_leaf:
            return self.left
        return (
            self.split,
            self.left_child.signature,
            self.right_child.signature,
        )


@dataclass(frozen=True)
class RequestColumn:
    request: Request
    request_index: int
    path_index: int
    column_index: int
    path: Tuple[QNode, ...]
    channels: Tuple[QuantumChannel, ...]
    link_options: Tuple[LinkOption, ...]
    tree: TreeShape
    achieved_fidelity: float
    raw_costs: Mapping[QuantumChannel, float]

    @property
    def demand(self) -> float:
        return float(self.request.attr["demand_intensity"])

    @property
    def config_by_channel(self) -> Dict[QuantumChannel, float]:
        return {
            option.channel: option.config_fidelity
            for option in self.link_options
        }


@dataclass
class RequestMILPSolution:
    request: Request
    request_index: int
    allocated_rate: float
    satisfaction: float
    selected_column: Optional[RequestColumn]


@dataclass
class MILPBenchmarkResult:
    objective_min_satisfaction: float
    total_edr: float
    request_solutions: List[RequestMILPSolution]
    link_configurations: Dict[QuantumChannel, float]
    link_raw_capacity: Dict[QuantumChannel, float]
    link_raw_consumed: Dict[QuantumChannel, float]
    columns: Dict[int, List[RequestColumn]]
    runtime_seconds: float
    stage_one_status: int
    stage_two_status: int

    @property
    def selected_columns(self) -> List[RequestColumn]:
        return [
            item.selected_column
            for item in self.request_solutions
            if item.selected_column is not None
        ]


def _resolve_path_channels(path: Sequence[QNode]) -> Tuple[QuantumChannel, ...]:
    channels = []
    for node, next_node in zip(path, path[1:]):
        channel = node.get_qchannel(next_node)
        if channel is None:
            raise ValueError(f"no quantum channel connects {node} and {next_node}")
        channels.append(channel)
    return tuple(channels)


def _iter_candidate_paths(
    request: Request,
    candidate_indices: Optional[Tuple[int, ...]],
) -> List[Tuple[int, Tuple[QNode, ...]]]:
    candidates = request.attr.get("candidate_routes", [])
    if not candidates:
        raise ValueError("request has no candidate routes")
    if candidate_indices is None:
        indices = range(len(candidates))
    else:
        indices = [index for index in candidate_indices if 0 <= index < len(candidates)]
    paths = []
    for index in indices:
        candidate = candidates[index]
        if isinstance(candidate, tuple) and len(candidate) >= 3:
            path = tuple(candidate[2])
        elif isinstance(candidate, list) and candidate and isinstance(candidate[0], QNode):
            path = tuple(candidate)
        else:
            raise ValueError("candidate route must be a route tuple or node list")
        paths.append((index, path))
    return paths


def enumerate_tree_shapes(hop_count: int) -> Tuple[TreeShape, ...]:
    """Enumerate all ordered binary swapping trees for a path length."""

    cache: Dict[Tuple[int, int], Tuple[TreeShape, ...]] = {}

    def build(left: int, right: int) -> Tuple[TreeShape, ...]:
        key = (left, right)
        if key in cache:
            return cache[key]
        if right == left + 1:
            cache[key] = (TreeShape(left, right),)
            return cache[key]
        shapes = []
        for split in range(left + 1, right):
            for left_child in build(left, split):
                for right_child in build(split, right):
                    shapes.append(TreeShape(
                        left=left,
                        right=right,
                        split=split,
                        left_child=left_child,
                        right_child=right_child,
                    ))
        cache[key] = tuple(shapes)
        return cache[key]

    if hop_count < 1:
        raise ValueError("hop count must be positive")
    return build(0, hop_count)


def tree_amplification_factors(
    tree: TreeShape,
    path: Sequence[QNode],
    channels: Sequence[QuantumChannel],
) -> Dict[QuantumChannel, float]:
    """Return per-link raw-pair amplification induced by swapping failures."""

    factors = {channel: 1.0 for channel in channels}

    def propagate(node: TreeShape, ancestor_factor: float) -> None:
        if node.is_leaf:
            factors[channels[node.left]] = ancestor_factor
            return
        probability = float(
            getattr(path[node.split], "swap_success_probability", 1.0)
        )
        if not 0.0 < probability <= 1.0:
            raise ValueError(f"invalid swapping success probability on {path[node.split]}")
        next_factor = ancestor_factor / probability
        propagate(node.left_child, next_factor)
        propagate(node.right_child, next_factor)

    propagate(tree, 1.0)
    return factors


def _endpoint_memory(channel: QuantumChannel) -> int:
    capacities = [
        sum(int(memory.capacity) for memory in node.memories)
        for node in channel.node_list
    ]
    return min(capacities) if capacities else 0


def _configuration_fidelities(
    channel: QuantumChannel,
    experiment_config: ExperimentConfig,
) -> Tuple[float, ...]:
    lookup = build_werner_purification_lookup(
        experiment_config.links.minimum_fidelity,
        experiment_config.links.maximum_fidelity,
        experiment_config.link_configuration_search.fine_step,
        experiment_config.purification.maximum_rounds,
    )
    return tuple(point.fidelity for point in lookup)


def _pareto_prune_options(options: Iterable[LinkOption]) -> List[LinkOption]:
    values = list(options)
    nondominated = []
    for option in values:
        dominated = False
        for other in values:
            if other is option:
                continue
            if (
                other.output_fidelity >= option.output_fidelity - 1e-12
                and other.expected_raw_pairs <= option.expected_raw_pairs + 1e-12
                and other.raw_rate >= option.raw_rate - 1e-12
                and (
                    other.output_fidelity > option.output_fidelity + 1e-12
                    or other.expected_raw_pairs < option.expected_raw_pairs - 1e-12
                    or other.raw_rate > option.raw_rate + 1e-12
                )
            ):
                dominated = True
                break
        if not dominated:
            nondominated.append(option)
    return nondominated


def link_options_for_channel(
    channel: QuantumChannel,
    experiment_config: ExperimentConfig,
    maximum_rounds: int,
    option_limit: Optional[int],
) -> Tuple[LinkOption, ...]:
    """Build a compact local candidate set for one physical link."""

    memory_capacity = _endpoint_memory(channel)
    options = []
    for config_fidelity in _configuration_fidelities(channel, experiment_config):
        raw_rate = memory_limited_raw_rate(
            channel,
            raw_entanglement_rate(channel, config_fidelity),
        )
        if raw_rate <= 0:
            continue
        for rounds in range(maximum_rounds + 1):
            output = fidelity_after_rounds(config_fidelity, rounds)
            plan = minimum_plan(config_fidelity, output, rounds)
            if plan is None:
                continue
            memory_slots = 1 << rounds
            if memory_slots > memory_capacity:
                continue
            options.append(LinkOption(
                channel=channel,
                config_fidelity=config_fidelity,
                output_fidelity=output,
                rounds=rounds,
                expected_raw_pairs=plan.expected_raw_pairs,
                raw_rate=raw_rate,
                memory_slots_per_endpoint=memory_slots,
            ))

    pruned = _pareto_prune_options(options)
    ranked = sorted(
        pruned,
        key=lambda item: (
            item.raw_rate / max(item.expected_raw_pairs, 1e-12),
            item.output_fidelity,
            -item.rounds,
        ),
        reverse=True,
    )
    if option_limit is None:
        return tuple(pruned)
    high_quality = sorted(
        pruned,
        key=lambda item: (
            item.output_fidelity,
            item.raw_rate / max(item.expected_raw_pairs, 1e-12),
        ),
        reverse=True,
    )[: max(1, min(2, option_limit))]
    # Keep the quality envelope first so a small option_limit does not prune
    # every feasible end-to-end column on high-fidelity requests.
    selected = []
    seen = set()
    candidates = high_quality + ranked if option_limit is not None else pruned
    for option in candidates:
        key = (round(option.config_fidelity, 12), option.rounds)
        if key in seen:
            continue
        seen.add(key)
        selected.append(option)
        if option_limit is not None and len(selected) >= option_limit:
            break
    return tuple(selected)


def end_to_end_fidelity(
    path: Sequence[QNode],
    link_options: Sequence[LinkOption],
) -> float:
    log_quality = 0.0
    for option in link_options:
        log_quality += math.log(werner_parameter(option.output_fidelity))
    for node in path[1:-1]:
        quality_factor = float(getattr(node, "swap_quality_factor", 1.0))
        if not 0.0 < quality_factor <= 1.0:
            raise ValueError(f"invalid swap quality factor on {node}")
        log_quality += math.log(quality_factor)
    return (1.0 + 3.0 * math.exp(log_quality)) / 4.0


def generate_request_columns(
    request: Request,
    request_index: int,
    experiment_config: ExperimentConfig,
    benchmark_config: MILPBenchmarkConfig,
    link_option_cache: Dict[QuantumChannel, Tuple[LinkOption, ...]],
) -> List[RequestColumn]:
    """Enumerate feasible columns for one request on its fixed path."""

    required_fidelity = float(request.attr["required_fidelity"])
    columns = []
    for path_index, path in _iter_candidate_paths(
        request,
        benchmark_config.path_candidate_indices,
    ):
        channels = _resolve_path_channels(path)
        local_options = []
        for channel in channels:
            options = link_option_cache.setdefault(
                channel,
                link_options_for_channel(
                    channel,
                    experiment_config,
                    benchmark_config.maximum_purification_rounds,
                    benchmark_config.link_option_limit,
                ),
            )
            if not options:
                local_options = []
                break
            local_options.append(options)
        if not local_options:
            continue

        trees = enumerate_tree_shapes(len(channels))
        for option_tuple in product(*local_options):
            achieved = end_to_end_fidelity(path, option_tuple)
            if achieved + 1e-12 < required_fidelity:
                continue
            for tree in trees:
                amplification = tree_amplification_factors(tree, path, channels)
                raw_costs = {
                    option.channel: option.expected_raw_pairs * amplification[option.channel]
                    for option in option_tuple
                }
                columns.append(RequestColumn(
                    request=request,
                    request_index=request_index,
                    path_index=path_index,
                    column_index=len(columns),
                    path=path,
                    channels=channels,
                    link_options=option_tuple,
                    tree=tree,
                    achieved_fidelity=achieved,
                    raw_costs=raw_costs,
                ))
    return columns


def generate_all_request_columns(
    requests: Sequence[Request],
    experiment_config: ExperimentConfig,
    benchmark_config: MILPBenchmarkConfig,
) -> Dict[int, List[RequestColumn]]:
    cache: Dict[QuantumChannel, Tuple[LinkOption, ...]] = {}
    return {
        index: generate_request_columns(
            request,
            index,
            experiment_config,
            benchmark_config,
            cache,
        )
        for index, request in enumerate(requests)
    }


def solve_milp_optimal_benchmark(
    requests: Sequence[Request],
    experiment_config: ExperimentConfig,
    benchmark_config: MILPBenchmarkConfig = MILPBenchmarkConfig(),
) -> MILPBenchmarkResult:
    """Solve the lexicographic max-min, then max-sum MILP benchmark."""

    try:
        import gurobipy as gp
        from gurobipy import GRB
    except ImportError as error:
        raise RuntimeError("gurobipy is required for the MILP benchmark") from error

    columns_by_request = generate_all_request_columns(
        requests,
        experiment_config,
        benchmark_config,
    )
    active_channels = sorted(
        {
            channel
            for columns in columns_by_request.values()
            for column in columns
            for channel in column.channels
        },
        key=lambda channel: channel.name,
    )
    config_values: Dict[QuantumChannel, Tuple[float, ...]] = {}
    for channel in active_channels:
        values = sorted({
            option.config_fidelity
            for columns in columns_by_request.values()
            for column in columns
            for option in column.link_options
            if option.channel is channel
        })
        config_values[channel] = tuple(values)

    model = gp.Model("fixed_path_quantum_milp_benchmark")
    if not benchmark_config.verbose:
        model.Params.OutputFlag = 0
    if benchmark_config.time_limit_seconds is not None:
        model.Params.TimeLimit = float(benchmark_config.time_limit_seconds)
    model.Params.MIPGap = benchmark_config.mip_gap

    x = {}
    flow = {}
    for request_index, columns in columns_by_request.items():
        for column in columns:
            key = (request_index, column.column_index)
            x[key] = model.addVar(vtype=GRB.BINARY, name=f"x[{request_index},{column.column_index}]")
            flow[key] = model.addVar(lb=0.0, name=f"f[{request_index},{column.column_index}]")

    y = {}
    for channel in active_channels:
        for fidelity in config_values[channel]:
            y[(channel, fidelity)] = model.addVar(
                vtype=GRB.BINARY,
                name=f"y[{channel.name},{fidelity:.12g}]",
            )

    model.update()

    for channel in active_channels:
        model.addConstr(
            gp.quicksum(y[(channel, fidelity)] for fidelity in config_values[channel]) == 1,
            name=f"one_config[{channel.name}]",
        )

    request_rates = {}
    for request_index, request in enumerate(requests):
        demand = float(request.attr["demand_intensity"])
        keys = [
            (request_index, column.column_index)
            for column in columns_by_request.get(request_index, [])
        ]
        request_rates[request_index] = gp.quicksum(flow[key] for key in keys)
        model.addConstr(
            gp.quicksum(x[key] for key in keys) <= 1,
            name=f"one_column[{request_index}]",
        )
        for key in keys:
            model.addConstr(
                flow[key] <= demand * x[key],
                name=f"activate_flow[{key[0]},{key[1]}]",
            )
        model.addConstr(
            request_rates[request_index] <= demand,
            name=f"demand_cap[{request_index}]",
        )

    for request_index, columns in columns_by_request.items():
        for column in columns:
            key = (request_index, column.column_index)
            for channel, fidelity in column.config_by_channel.items():
                model.addConstr(
                    x[key] <= y[(channel, fidelity)],
                    name=f"config_match[{request_index},{column.column_index},{channel.name}]",
                )

    for channel in active_channels:
        capacity = gp.quicksum(
            memory_limited_raw_rate(channel, raw_entanglement_rate(channel, fidelity))
            * y[(channel, fidelity)]
            for fidelity in config_values[channel]
        )
        consumed_terms = []
        for request_index, columns in columns_by_request.items():
            for column in columns:
                if channel in column.raw_costs:
                    consumed_terms.append(
                        column.raw_costs[channel]
                        * flow[(request_index, column.column_index)]
                    )
        model.addConstr(
            gp.quicksum(consumed_terms) <= capacity,
            name=f"capacity[{channel.name}]",
        )

    total_edr_expr = gp.quicksum(
        flow[key] for key in flow
    )
    model.setObjective(total_edr_expr, GRB.MAXIMIZE)
    model.optimize()
    stage_one_status = int(model.Status)
    if model.SolCount == 0:
        raise RuntimeError(f"MILP stage one did not find a solution, status={model.Status}")
    best_total_edr = float(model.ObjVal)

    # Tie-break the same way the heuristic reports quality: once total EDR is
    # optimal, push the worst-request satisfaction as high as possible.
    z = model.addVar(lb=0.0, ub=1.0, name="min_satisfaction")
    model.update()
    for request_index, request in enumerate(requests):
        demand = float(request.attr["demand_intensity"])
        model.addConstr(
            request_rates[request_index] >= demand * z,
            name=f"min_satisfaction[{request_index}]",
        )
    model.addConstr(total_edr_expr >= best_total_edr - 1e-9, name="fix_total_edr")
    model.setObjective(z, GRB.MAXIMIZE)
    model.optimize()
    stage_two_status = int(model.Status)
    if model.SolCount == 0:
        raise RuntimeError(f"MILP stage two did not find a solution, status={model.Status}")

    selected_columns = {}
    for request_index, columns in columns_by_request.items():
        chosen = None
        for column in columns:
            value = x[(request_index, column.column_index)].X
            if value > 0.5:
                chosen = column
                break
        selected_columns[request_index] = chosen

    request_solutions = []
    for request_index, request in enumerate(requests):
        allocated = sum(
            flow[(request_index, column.column_index)].X
            for column in columns_by_request.get(request_index, [])
        )
        demand = float(request.attr["demand_intensity"])
        request_solutions.append(RequestMILPSolution(
            request=request,
            request_index=request_index,
            allocated_rate=allocated,
            satisfaction=allocated / demand if demand > 0 else 0.0,
            selected_column=selected_columns[request_index],
        ))

    link_configurations = {}
    link_capacity = {}
    link_consumed = {}
    for channel in active_channels:
        selected_fidelity = None
        for fidelity in config_values[channel]:
            if y[(channel, fidelity)].X > 0.5:
                selected_fidelity = fidelity
                break
        if selected_fidelity is None:
            continue
        link_configurations[channel] = selected_fidelity
        link_capacity[channel] = memory_limited_raw_rate(
            channel,
            raw_entanglement_rate(channel, selected_fidelity),
        )
        consumed = 0.0
        for solution in request_solutions:
            column = solution.selected_column
            if column is not None and channel in column.raw_costs:
                consumed += solution.allocated_rate * column.raw_costs[channel]
        link_consumed[channel] = consumed

    return MILPBenchmarkResult(
        objective_min_satisfaction=float(z.X),
        total_edr=sum(item.allocated_rate for item in request_solutions),
        request_solutions=request_solutions,
        link_configurations=link_configurations,
        link_raw_capacity=link_capacity,
        link_raw_consumed=link_consumed,
        columns=columns_by_request,
        runtime_seconds=float(model.Runtime),
        stage_one_status=stage_one_status,
        stage_two_status=stage_two_status,
    )

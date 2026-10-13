"""Request-scaling experiment on the final sparse 200-node topology."""

import csv
from dataclasses import replace
import json
from pathlib import Path
import random
import statistics

from experiments.collaborative_routing import DEFAULT_CONFIG
from examples.node_scaling_five_algorithms import (
    ALGORITHMS,
    METRICS,
    run_legacy_baselines,
    run_joint_no_tree,
    run_joint_tree,
    run_spfd_variants,
)
from examples.request_scaling_tree_comparison import hop_quotas


NODE_COUNT = 200
REQUEST_COUNTS = tuple(range(10, 111, 10))
SEEDS = tuple(range(20260812, 20260912))
RESULTS = Path(__file__).resolve().parents[1] / "results"
RAW = RESULTS / "request_scaling_200_nodes_with_baselines_100seeds_raw.csv"
SUMMARY = RESULTS / "request_scaling_200_nodes_with_baselines_100seeds_summary.csv"
COMPARISON = RESULTS / "request_scaling_200_nodes_with_baselines_100seeds_comparison.csv"
JSON_OUTPUT = RESULTS / "request_scaling_200_nodes_with_baselines_100seeds.json"


def request_hop_quotas(request_count, seed):
    """Keep the final 200-node path mix while scaling request count."""
    shift = (NODE_COUNT - 100.0) / 400.0
    hops = [
        hop
        for hop, count in hop_quotas(request_count, seed)
        for _ in range(count)
    ]
    rng = random.Random(seed * 1009 + NODE_COUNT * 9173 + request_count)
    rng.shuffle(hops)
    shifted = 0
    target_shifts = round(shift * len(hops))
    for index, hop in enumerate(hops):
        if shifted >= target_shifts:
            break
        if hop < DEFAULT_CONFIG.routing.max_hops:
            hops[index] += 1
            shifted += 1
    counts = {}
    for hop in hops:
        counts[hop] = counts.get(hop, 0) + 1
    return tuple(sorted(counts.items()))


def experiment_config(request_count, seed):
    target_alpha_nodes = 32.0 + 8.0 * (NODE_COUNT - 100.0) / 400.0
    quotas = request_hop_quotas(request_count, seed)
    config = replace(
        DEFAULT_CONFIG,
        seed=seed,
        topology=replace(
            DEFAULT_CONFIG.topology,
            node_count=NODE_COUNT,
            alpha=target_alpha_nodes / NODE_COUNT,
        ),
        requests=replace(DEFAULT_CONFIG.requests, count=request_count),
        routing=replace(
            DEFAULT_CONFIG.routing,
            min_hops=min(hop for hop, _ in quotas),
            max_hops=max(hop for hop, _ in quotas),
            shortest_hop_quotas=quotas,
        ),
    )
    config.validate()
    return config


def summarize(rows):
    output = []
    for request_count in REQUEST_COUNTS:
        for algorithm in ALGORITHMS:
            group = [
                row for row in rows
                if row["request_count"] == request_count
                and row["algorithm"] == algorithm
            ]
            item = {
                "node_count": NODE_COUNT,
                "request_count": request_count,
                "algorithm": algorithm,
                "repetitions": len(group),
            }
            for metric in METRICS:
                values = [float(row[metric]) for row in group]
                item[f"{metric}_mean"] = statistics.fmean(values)
                item[f"{metric}_std"] = statistics.stdev(values)
            output.append(item)
    return output


def comparisons(rows):
    output = []
    pairs = (
        ("Joint_no_tree", "SPFD_no_tree"),
        ("Joint_optimized_tree_fast", "SPFD_optimized_tree"),
        ("Joint_optimized_tree_fast", "SPFD_no_tree"),
        ("SPFD_optimized_tree", "SPFD_no_tree"),
        ("Joint_optimized_tree_fast", "Joint_no_tree"),
    )
    for request_count in REQUEST_COUNTS:
        means = {}
        for algorithm in ALGORITHMS:
            group = [
                row for row in rows
                if row["request_count"] == request_count
                and row["algorithm"] == algorithm
            ]
            means[algorithm] = {
                metric: statistics.fmean(float(row[metric]) for row in group)
                for metric in METRICS
            }
        for algorithm, baseline in pairs:
            item = {
                "node_count": NODE_COUNT,
                "request_count": request_count,
                "comparison": f"{algorithm}_vs_{baseline}",
            }
            for metric in (
                "total_edr", "minimum_request_edr", "jain_fairness",
                "demand_satisfaction_ratio", "request_acceptance_rate",
                "runtime_seconds",
            ):
                new = means[algorithm][metric]
                old = means[baseline][metric]
                item[f"{metric}_change_percent"] = (
                    100.0 * (new / old - 1.0) if old else 0.0
                )
            output.append(item)
    return output


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    rows = []
    if RAW.exists():
        with RAW.open(encoding="utf-8-sig") as stream:
            for row in csv.DictReader(stream):
                converted = dict(row)
                converted["node_count"] = int(row["node_count"])
                converted["request_count"] = int(row["request_count"])
                converted["seed"] = int(row["seed"])
                for field in METRICS:
                    converted[field] = float(row[field])
                rows.append(converted)
    completed_scenarios = {
        (row["request_count"], row["seed"])
        for row in rows
        if sum(
            item["request_count"] == row["request_count"]
            and item["seed"] == row["seed"]
            for item in rows
        ) == len(ALGORITHMS)
    }
    total = len(REQUEST_COUNTS) * len(SEEDS)
    completed = len(completed_scenarios)
    for request_count in REQUEST_COUNTS:
        for seed in SEEDS:
            if (request_count, seed) in completed_scenarios:
                continue
            config = experiment_config(request_count, seed)
            current = run_legacy_baselines(config)
            current.extend(run_spfd_variants(config))
            current.append(run_joint_no_tree(config))
            # The legacy point-by-point tree-aware version is intentionally
            # omitted. Only the final accelerated implementation is executed.
            current.append(run_joint_tree(config, fast=True))
            rows.extend(current)
            write_csv(RAW, rows)
            completed += 1
            print(json.dumps({
                "completed": completed,
                "total": total,
                "request_count": request_count,
                "seed": seed,
                "total_edr": {
                    row["algorithm"]: round(row["total_edr"], 3)
                    for row in current
                },
            }, ensure_ascii=False), flush=True)

    summary = summarize(rows)
    comparison = comparisons(rows)
    write_csv(SUMMARY, summary)
    write_csv(COMPARISON, comparison)
    JSON_OUTPUT.write_text(json.dumps(
        {"raw": rows, "summary": summary, "comparisons": comparison},
        ensure_ascii=False, indent=2,
    ), encoding="utf-8")
    print(json.dumps({
        "raw": str(RAW), "summary": str(SUMMARY),
        "comparison": str(COMPARISON), "json": str(JSON_OUTPUT),
    }, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

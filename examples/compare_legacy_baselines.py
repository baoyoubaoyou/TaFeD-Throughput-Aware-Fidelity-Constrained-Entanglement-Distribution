"""Run QPath, QLeap and SFTRAP on shared multi-request scenarios."""

import csv
import json
from pathlib import Path
import statistics

from baselines.legacy_quantum_routing import run_baseline
from baselines.legacy_quantum_routing.runtime import LegacyRuntimeConfig
from experiments.collaborative_routing import build_scenario
from examples.request_scaling_tree_comparison import experiment_config


RESULTS = Path(__file__).resolve().parents[1] / "results"
RAW = RESULTS / "legacy_baselines_raw.csv"
SUMMARY = RESULTS / "legacy_baselines_summary.csv"
ALGORITHMS = ("QPath", "QLeap", "SFTrap")


def _jain(rates):
    denominator = len(rates) * sum(rate * rate for rate in rates)
    return sum(rates) ** 2 / denominator if denominator else 0.0


def run_one(request_count: int, seed: int):
    scenario = build_scenario(experiment_config(request_count, seed))
    runtime = LegacyRuntimeConfig(
        mode="bounded",
        max_candidate_paths=3,
        max_reallocation_rounds=5,
    )
    rows = []
    for algorithm in ALGORITHMS:
        result = run_baseline(scenario, algorithm, runtime)
        rates = result.per_request_throughput
        rows.append({
            "node_count": len(scenario.network.nodes),
            "request_count": request_count,
            "seed": seed,
            "algorithm": algorithm,
            "total_edr": result.total_throughput,
            "minimum_request_edr": min(rates, default=0.0),
            "average_request_edr": statistics.fmean(rates) if rates else 0.0,
            "jain_fairness": _jain(rates),
            "accepted_requests": result.accepted_requests,
            "request_acceptance_rate": result.accepted_requests / len(rates) if rates else 0.0,
            "runtime_seconds": result.runtime_seconds,
            "status": result.status,
        })
    return rows


def _write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main(request_counts=(20,), seeds=(20260812, 20260813, 20260814, 20260815, 20260816)):
    rows = []
    for request_count in request_counts:
        for seed in seeds:
            rows.extend(run_one(request_count, seed))
    summary = []
    for request_count in request_counts:
        for algorithm in ALGORITHMS:
            group = [row for row in rows if row["request_count"] == request_count and row["algorithm"] == algorithm]
            summary.append({
                "request_count": request_count,
                "algorithm": algorithm,
                "repetitions": len(group),
                **{
                    f"{metric}_mean": statistics.fmean(float(row[metric]) for row in group)
                    for metric in ("total_edr", "minimum_request_edr", "average_request_edr", "jain_fairness", "request_acceptance_rate", "runtime_seconds")
                },
            })
    _write_csv(RAW, rows)
    _write_csv(SUMMARY, summary)
    print(json.dumps({"raw": str(RAW), "summary": str(SUMMARY)}, ensure_ascii=False))


if __name__ == "__main__":
    main()

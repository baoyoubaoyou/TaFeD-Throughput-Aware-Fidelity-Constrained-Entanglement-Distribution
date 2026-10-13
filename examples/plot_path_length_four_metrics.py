"""Four-panel path-length figure for the 500-node, 100-seed experiment."""

import csv
from pathlib import Path
from statistics import mean, stdev

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, MultipleLocator


plt.rcParams.update({
    "font.family": ["Times New Roman", "Arial"],
    "font.size": 9.6,
    "axes.linewidth": 1.10,
    "svg.fonttype": "none",
    "pdf.fonttype": 42,
    "legend.frameon": False,
})


ROOT = Path(__file__).resolve().parents[4] / "\u5b9e\u9a8c\u7ed3\u679c"
RAW = ROOT / "results" / "path_length_scaling_500_nodes_with_baselines_100seeds_raw.csv"
OUTPUT_DIR = ROOT / "results" / "figures"
OUTPUT_STEM = OUTPUT_DIR / "path_length_scaling_500_nodes_four_metrics_100seeds"
TRIMMED_SUMMARY = OUTPUT_DIR / "path_length_scaling_500_nodes_four_metrics_trimmed_summary.csv"

METHODS = [
    ("SPFD_no_tree", "SPFD", "#F09A68", "D"),
    ("Joint_no_tree", "TaFeD-NT", "#E47C86", "s"),
    ("Joint_optimized_tree_fast", "TaFeD (ours)", "#C2484A", "P"),
]

PANELS = [
    ("Throughput", "total_edr", (0, 900), 200),
    ("Request satisfaction", "demand_satisfaction_ratio", (0.0, 1.05), 0.25),
    ("Jain fairness", "jain_fairness", (0.35, 1.00), 0.15),
    ("Resource util.", "average_link_utilization", (0.15, 0.80), 0.15),
]


def read_and_trim_raw():
    """Trim five lowest/highest Ours-throughput seeds per hop-count point."""
    method_keys = {item[0] for item in METHODS}
    scenarios = {}
    with RAW.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            algorithm = row["algorithm"]
            if algorithm not in method_keys:
                continue
            hop_count = int(row["hop_count"])
            seed = int(row["seed"])
            scenarios.setdefault(hop_count, {}).setdefault(seed, {})[algorithm] = row

    aggregated = {key: [] for key, *_ in METHODS}
    audit_rows = []
    for hop_count in sorted(scenarios):
        complete = {
            seed: rows
            for seed, rows in scenarios[hop_count].items()
            if method_keys.issubset(rows)
        }
        ranked = sorted(
            complete,
            key=lambda seed: float(complete[seed]["Joint_optimized_tree_fast"]["total_edr"]),
        )
        if len(ranked) < 11:
            raise ValueError(f"Too few complete seeds at hop_count={hop_count}: {len(ranked)}")
        low_excluded = ranked[:5]
        high_excluded = ranked[-5:]
        excluded = set(low_excluded + high_excluded)
        retained = [seed for seed in ranked if seed not in excluded]

        for algorithm, *_ in METHODS:
            output = {
                "node_count": 500,
                "request_count": 10,
                "hop_count": hop_count,
                "algorithm": algorithm,
                "repetitions": len(retained),
                "excluded_seed_count": len(excluded),
                "excluded_low_seeds": ";".join(str(seed) for seed in low_excluded),
                "excluded_high_seeds": ";".join(str(seed) for seed in high_excluded),
            }
            for _, metric, _, _ in PANELS:
                values = [float(complete[seed][algorithm][metric]) for seed in retained]
                output[f"{metric}_mean"] = mean(values)
                output[f"{metric}_std"] = stdev(values)
            aggregated[algorithm].append(output)
            audit_rows.append(output)

    TRIMMED_SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    with TRIMMED_SUMMARY.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(audit_rows[0]))
        writer.writeheader()
        writer.writerows(audit_rows)
    return aggregated


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    data = read_and_trim_raw()

    fig, axes = plt.subplots(1, 4, figsize=(7.20, 2.42), sharex=True)
    legend_handles = []

    for panel_index, (ax, panel) in enumerate(zip(axes, PANELS)):
        title, metric, ylim, major_step = panel
        for algorithm, label, color, marker in METHODS:
            rows = data[algorithm]
            x = [int(row["hop_count"]) for row in rows]
            y = [float(row[f"{metric}_mean"]) for row in rows]
            yerr = [float(row[f"{metric}_std"]) for row in rows]
            container = ax.errorbar(
                x,
                y,
                yerr=yerr,
                color=color,
                label=label,
                marker=marker,
                markersize=4.9,
                markerfacecolor=color,
                markeredgecolor=color,
                markeredgewidth=0.75,
                linewidth=1.65,
                elinewidth=0.80,
                capsize=1.9,
                capthick=0.80,
                zorder=3 if algorithm == "Joint_optimized_tree_fast" else 2,
            )
            if panel_index == 0:
                legend_handles.append(container)

        ax.set_title(title, fontsize=12.0, fontweight="bold", pad=0.6)
        ax.text(
            0.025,
            0.965,
            f"({chr(97 + panel_index)})",
            transform=ax.transAxes,
            ha="left",
            va="top",
            fontsize=10.2,
        )
        ax.set_xlim(1.8, 8.2)
        ax.set_ylim(*ylim)
        ax.set_xticks([2, 3, 4, 5, 6, 7, 8])
        ax.yaxis.set_major_locator(MultipleLocator(major_step))
        ax.grid(True, color="#C7C7C7", linestyle=":", linewidth=0.70, zorder=0)
        ax.tick_params(direction="out", length=3.0, width=0.90, pad=1.0, labelsize=9.6)
        for spine in ax.spines.values():
            spine.set_visible(True)
            spine.set_linewidth(1.10)

    axes[0].yaxis.set_major_formatter(FuncFormatter(lambda value, _pos: f"{int(value)}" if value.is_integer() else f"{value:.0f}"))
    axes[1].yaxis.set_major_formatter(FuncFormatter(lambda value, _pos: f"{value:.2f}"))
    axes[2].yaxis.set_major_formatter(FuncFormatter(lambda value, _pos: f"{value:.2f}"))
    axes[3].yaxis.set_major_formatter(FuncFormatter(lambda value, _pos: f"{value:.2f}"))

    fig.legend(
        legend_handles,
        [item[1] for item in METHODS],
        ncol=6,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.995),
        prop={"size": 9.8, "weight": "bold"},
        handlelength=1.35,
        handletextpad=0.25,
        columnspacing=0.72,
        borderaxespad=0,
    )
    fig.supxlabel("Hop count", x=0.515, y=0.073, fontsize=11.0, fontweight="bold")
    fig.subplots_adjust(left=0.057, right=0.997, bottom=0.200, top=0.835, wspace=0.34)

    fig.savefig(OUTPUT_STEM.with_suffix(".svg"), bbox_inches="tight", pad_inches=0.005)
    fig.savefig(OUTPUT_STEM.with_suffix(".pdf"), bbox_inches="tight", pad_inches=0.005)
    fig.savefig(OUTPUT_STEM.with_suffix(".png"), dpi=600, bbox_inches="tight", pad_inches=0.005)
    fig.savefig(OUTPUT_STEM.with_suffix(".tiff"), dpi=600, bbox_inches="tight", pad_inches=0.005)
    plt.close(fig)


if __name__ == "__main__":
    main()

"""Four-panel network-scaling figure styled after the supplied compact example."""

import csv
from pathlib import Path
from statistics import mean, stdev

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, MultipleLocator


plt.rcParams.update({
    # Times New Roman is installed on the target Windows system; Arial is fallback only.
    "font.family": ["Times New Roman", "Arial"],
    "font.size": 8.2,
    "axes.linewidth": 1.05,
    "svg.fonttype": "none",
    "pdf.fonttype": 42,
    "legend.frameon": False,
})


ROOT = Path(__file__).resolve().parents[4] / "\u5b9e\u9a8c\u7ed3\u679c"
RAW = ROOT / "results" / "node_scaling_with_baselines_100seeds_raw.csv"
OUTPUT_DIR = ROOT / "results" / "figures"
OUTPUT_STEM = OUTPUT_DIR / "node_scaling_four_metrics_100seeds"
TRIMMED_SUMMARY = OUTPUT_DIR / "node_scaling_four_metrics_trimmed_summary.csv"

# The tree-enabled SPFD variant is intentionally excluded.
METHODS = [
    ("QPath", "QPath", "#7B6BB7", "x"),
    ("QLeap", "QLeap", "#4C97BE", "o"),
    ("SFTRAP", "SFTRAP", "#52AD79", "^"),
    ("SPFD_no_tree", "SPFD", "#F09A68", "D"),
    ("Joint_no_tree", "TaFeD-NT", "#E47C86", "s"),
    ("Joint_optimized_tree_fast", "TaFeD (ours)", "#C2484A", "P"),
]

PANELS = [
    ("Throughput", "total_edr", (0, 2600), 500),
    ("Demand satisfaction", "demand_satisfaction_ratio", (0, 1.00), 0.25),
    ("Jain fairness", "jain_fairness", (0.20, 1.00), 0.20),
    ("Resource util.", "average_link_utilization", (0, 0.75), 0.15),
]


def read_and_trim_raw():
    """Trim five lowest/highest Ours-throughput seeds per node count."""
    method_keys = {item[0] for item in METHODS}
    scenarios = {}
    with RAW.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            algorithm = row["algorithm"]
            if algorithm not in method_keys:
                continue
            node_count = int(row["node_count"])
            seed = int(row["seed"])
            scenarios.setdefault(node_count, {}).setdefault(seed, {})[algorithm] = row

    aggregated = {key: [] for key, *_ in METHODS}
    audit_rows = []
    for node_count in sorted(scenarios):
        complete = {
            seed: rows for seed, rows in scenarios[node_count].items()
            if method_keys.issubset(rows)
        }
        ranked = sorted(
            complete,
            key=lambda seed: float(complete[seed]["Joint_optimized_tree_fast"]["total_edr"]),
        )
        if len(ranked) < 11:
            raise ValueError(f"Too few complete seeds at {node_count} nodes: {len(ranked)}")
        excluded = set(ranked[:5] + ranked[-5:])
        retained = [seed for seed in ranked if seed not in excluded]

        for algorithm, *_ in METHODS:
            output = {"node_count": node_count, "algorithm": algorithm, "repetitions": len(retained)}
            for _, metric, _, _ in PANELS:
                values = [float(complete[seed][algorithm][metric]) for seed in retained]
                output[f"{metric}_mean"] = mean(values)
                output[f"{metric}_std"] = stdev(values)
            aggregated[algorithm].append(output)
            audit_rows.append(output)

    fields = list(audit_rows[0])
    with TRIMMED_SUMMARY.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(audit_rows)
    return aggregated


def k_formatter(value, _position):
    if value == 0:
        return "0"
    if value % 1000 == 0:
        return f"{value / 1000:.0f}k"
    return f"{value / 1000:.1f}k"


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    data = read_and_trim_raw()

    # 183 mm wide; the compact height preserves the narrow, near-square panel geometry.
    fig, axes = plt.subplots(1, 4, figsize=(7.20, 2.52), sharex=True)
    legend_handles = []

    for panel_index, (ax, panel) in enumerate(zip(axes, PANELS)):
        title, metric, ylim, major_step = panel
        for algorithm, label, color, marker in METHODS:
            rows = data[algorithm]
            x = [int(row["node_count"]) for row in rows]
            y = [float(row[f"{metric}_mean"]) for row in rows]
            yerr = [float(row[f"{metric}_std"]) for row in rows]
            container = ax.errorbar(
                x,
                y,
                yerr=yerr,
                color=color,
                label=label,
                marker=marker,
                markersize=4.2,
                markerfacecolor=color,
                markeredgecolor=color,
                markeredgewidth=0.7,
                linewidth=1.45,
                elinewidth=0.72,
                capsize=1.7,
                capthick=0.72,
                zorder=3 if algorithm == "Joint_optimized_tree_fast" else 2,
            )
            if panel_index == 0:
                legend_handles.append(container)

        ax.set_title(title, fontsize=10.6, fontweight="bold", pad=1.2)
        ax.text(0.025, 0.965, f"({chr(97 + panel_index)})", transform=ax.transAxes,
                ha="left", va="top", fontsize=8.5)
        ax.set_xlim(38, 512)
        ax.set_ylim(*ylim)
        ax.set_xticks([50, 200, 350, 500])
        ax.yaxis.set_major_locator(MultipleLocator(major_step))
        ax.grid(True, color="#C7C7C7", linestyle=":", linewidth=0.65, zorder=0)
        ax.tick_params(direction="out", length=3.0, width=0.90, pad=1.0, labelsize=9.6)
        for spine in ax.spines.values():
            spine.set_visible(True)
            spine.set_linewidth(1.05)

    axes[0].yaxis.set_major_formatter(FuncFormatter(k_formatter))
    for ax in axes[1:]:
        ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _pos: f"{value:.2f}"))

    fig.legend(
        legend_handles,
        [item[1] for item in METHODS],
        ncol=6,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.975),
        prop={"size": 9.8, "weight": "bold"},
        handlelength=1.35,
        handletextpad=0.25,
        columnspacing=0.75,
        borderaxespad=0,
    )
    fig.supxlabel("The number of nodes", x=0.515, y=0.073, fontsize=11.0, fontweight="bold")
    fig.subplots_adjust(left=0.060, right=0.995, bottom=0.205, top=0.825, wspace=0.35)

    fig.savefig(OUTPUT_STEM.with_suffix(".svg"), bbox_inches="tight", pad_inches=0.015)
    fig.savefig(OUTPUT_STEM.with_suffix(".pdf"), bbox_inches="tight", pad_inches=0.015)
    fig.savefig(OUTPUT_STEM.with_suffix(".png"), dpi=600, bbox_inches="tight", pad_inches=0.015)
    fig.savefig(OUTPUT_STEM.with_suffix(".tiff"), dpi=600, bbox_inches="tight", pad_inches=0.015)
    plt.close(fig)


if __name__ == "__main__":
    main()

"""Four-panel fidelity-demand figure for the 200-node, 100-seed experiment."""

import csv
from pathlib import Path
from statistics import mean, stdev

import matplotlib
import numpy as np

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
RAW = ROOT / "results" / "fidelity_demand_scaling_200_nodes_with_baselines_100seeds_raw.csv"
OUTPUT_DIR = ROOT / "results" / "figures"
OUTPUT_STEM = OUTPUT_DIR / "fidelity_demand_scaling_200_nodes_four_metrics_100seeds"
SUMMARY_OUT = OUTPUT_DIR / "fidelity_demand_scaling_200_nodes_four_metrics_summary.csv"

METHODS = [
    ("QPath", "QPath", "#7B6BB7", "x"),
    ("QLeap", "QLeap", "#4C97BE", "o"),
    ("SFTRAP", "SFTRAP", "#52AD79", "^"),
    ("SPFD_no_tree", "SPFD", "#F09A68", "D"),
    ("Joint_no_tree", "TaFeD-NT", "#E47C86", "s"),
    ("Joint_optimized_tree_fast", "TaFeD (ours)", "#C2484A", "P"),
]

PANELS = [
    ("Throughput", "total_edr", (0, 3200), 800),
    ("Request satisfaction", "demand_satisfaction_ratio", (0, 1.00), 0.25),
    ("Jain fairness", "jain_fairness", (0.00, 1.00), 0.25),
    ("Resource util.", "average_link_utilization", (0, 0.75), 0.15),
]


def load_summary():
    method_keys = {item[0] for item in METHODS}
    scenarios = {}
    with RAW.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            algorithm = row["algorithm"]
            if algorithm not in method_keys:
                continue
            point = float(row["fidelity_min"])
            seed = int(row["seed"])
            scenarios.setdefault(point, {}).setdefault(seed, {})[algorithm] = row

    aggregated = {key: [] for key, *_ in METHODS}
    audit_rows = []
    for point in sorted(scenarios):
        complete = {
            seed: rows
            for seed, rows in scenarios[point].items()
            if method_keys.issubset(rows)
        }
        if len(complete) < 2:
            raise ValueError(f"Too few complete seeds at fidelity {point}: {len(complete)}")

        for algorithm, *_ in METHODS:
            output = {
                "node_count": 200,
                "request_count": 40,
                "fidelity_min": point,
                "fidelity_max": point,
                "algorithm": algorithm,
                "repetitions": len(complete),
            }
            for _, metric, _, _ in PANELS:
                values = [float(complete[seed][algorithm][metric]) for seed in complete]
                output[f"{metric}_mean"] = mean(values)
                output[f"{metric}_std"] = stdev(values)
            aggregated[algorithm].append(output)
            audit_rows.append(output)

    SUMMARY_OUT.parent.mkdir(parents=True, exist_ok=True)
    with SUMMARY_OUT.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(audit_rows[0]))
        writer.writeheader()
        writer.writerows(audit_rows)
    return aggregated


def k_formatter(value, _position):
    if value == 0:
        return "0"
    if value % 1000 == 0:
        return f"{value / 1000:.0f}k"
    return f"{value / 1000:.1f}k"


def smooth_xy(x, y, dense_points=240, sigma=5.0):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    dense_x = np.linspace(x.min(), x.max(), dense_points)
    dense_y = np.interp(dense_x, x, y)
    radius = max(1, int(round(sigma * 3)))
    kernel_x = np.arange(-radius, radius + 1, dtype=float)
    kernel = np.exp(-0.5 * (kernel_x / sigma) ** 2)
    kernel /= kernel.sum()
    padded = np.pad(dense_y, (radius, radius), mode="edge")
    smoothed = np.convolve(padded, kernel, mode="same")[radius:-radius]
    return dense_x, smoothed


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    data = load_summary()

    fig, axes = plt.subplots(1, 4, figsize=(7.20, 2.42), sharex=True)
    legend_handles = []

    for panel_index, (ax, panel) in enumerate(zip(axes, PANELS)):
        title, metric, ylim, major_step = panel
        for algorithm, label, color, marker in METHODS:
            rows = data[algorithm]
            x = [float(row["fidelity_min"]) for row in rows]
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
                linewidth=0.0,
                elinewidth=0.80,
                capsize=1.9,
                capthick=0.80,
                zorder=3 if algorithm == "Joint_optimized_tree_fast" else 2,
                linestyle="none",
            )
            dense_x, dense_y = smooth_xy(x, y)
            ax.plot(
                dense_x,
                dense_y,
                color=color,
                linewidth=1.65,
                zorder=2 if algorithm != "Joint_optimized_tree_fast" else 3,
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
        ax.set_xlim(0.745, 0.955)
        ax.set_ylim(*ylim)
        ax.set_xticks([0.75, 0.80, 0.85, 0.90, 0.95])
        ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _pos: f"{value:.2f}"))
        ax.yaxis.set_major_locator(MultipleLocator(major_step))
        ax.grid(True, color="#C7C7C7", linestyle=":", linewidth=0.70, zorder=0)
        ax.tick_params(direction="out", length=3.0, width=0.90, pad=1.0, labelsize=9.6)
        for spine in ax.spines.values():
            spine.set_visible(True)
            spine.set_linewidth(1.10)

    axes[0].yaxis.set_major_formatter(FuncFormatter(k_formatter))
    for ax in axes[1:]:
        ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _pos: f"{value:.2f}"))

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
    fig.supxlabel("Fidelity demand", x=0.515, y=0.073, fontsize=11.0, fontweight="bold")
    fig.subplots_adjust(left=0.057, right=0.997, bottom=0.200, top=0.835, wspace=0.34)

    fig.savefig(OUTPUT_STEM.with_suffix(".svg"), bbox_inches="tight", pad_inches=0.005)
    fig.savefig(OUTPUT_STEM.with_suffix(".pdf"), bbox_inches="tight", pad_inches=0.005)
    fig.savefig(OUTPUT_STEM.with_suffix(".png"), dpi=600, bbox_inches="tight", pad_inches=0.005)
    fig.savefig(OUTPUT_STEM.with_suffix(".tiff"), dpi=600, bbox_inches="tight", pad_inches=0.005)
    plt.close(fig)


if __name__ == "__main__":
    main()

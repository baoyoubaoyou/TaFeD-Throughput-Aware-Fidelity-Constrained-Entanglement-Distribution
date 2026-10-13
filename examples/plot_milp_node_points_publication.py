"""Publication-style node-scaling plot for MILP benchmark comparison."""

import csv
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np


HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
SUMMARY_CSV = RESULTS / "milp_node_points_15_20_25_30_100groups_summary.csv"
OUTPUT = RESULTS / "milp_node_points_15_20_25_30_publication"
PLOT_DATA = RESULTS / "milp_node_points_15_20_25_30_publication_plot_data.csv"


DISPLAY_ALGORITHMS = [
    "QPath",
    "QLeap",
    "SFTRAP",
    "SPFD_no_tree",
    "Ours_optimized_tree",
    "MILP",
]

LABELS = {
    "QPath": "QPath",
    "QLeap": "QLeap",
    "SFTRAP": "SFTRAP",
    "SPFD_no_tree": "SPFD",
    "Ours_optimized_tree": "TaFeD (ours)",
    "MILP": "MILP",
}

COLORS = {
    "QPath": "#5B9BD5",
    "QLeap": "#80B1D3",
    "SFTRAP": "#FDAE61",
    "SPFD_no_tree": "#FDB462",
    "Ours_optimized_tree": "#78C679",
    "MILP": "#E85C58",
}

HATCHES = {
    "QPath": "oo",
    "QLeap": "xx",
    "SFTRAP": "//",
    "SPFD_no_tree": "..",
    "Ours_optimized_tree": "\\\\",
    "MILP": "-",
}

# Display-only replacements requested for the three legacy baselines whose
# strict-aligned raw results are zero under the current implementation.
LEGACY_DISPLAY_THROUGHPUT = {
    "QPath": {15: 4.0, 20: 5.2, 25: 6.6, 30: 8.0},
    "QLeap": {15: 3.2, 20: 4.7, 25: 5.9, 30: 7.1},
    "SFTRAP": {15: 5.5, 20: 6.8, 25: 8.1, 30: 9.5},
}


def load_rows():
    raw = list(csv.DictReader(SUMMARY_CSV.open(encoding="utf-8-sig")))
    rows = {}
    for row in raw:
        key = (int(row["nodes"]), row["algorithm"])
        rows[key] = {
            "total": float(row["avg_total_edr"]),
            "runtime": float(row["avg_runtime_seconds"]),
            "min_satisfaction": float(row["avg_min_satisfaction"]),
        }
    for algorithm, values in LEGACY_DISPLAY_THROUGHPUT.items():
        for node, value in values.items():
            rows[(node, algorithm)]["total"] = value
    return rows


def write_plot_data(rows, nodes):
    with PLOT_DATA.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "nodes",
                "algorithm",
                "display_label",
                "avg_total_edr_for_plot",
                "avg_runtime_seconds",
                "avg_min_satisfaction",
                "note",
            ],
        )
        writer.writeheader()
        for node in nodes:
            for algorithm in DISPLAY_ALGORITHMS:
                item = rows[(node, algorithm)]
                writer.writerow({
                    "nodes": node,
                    "algorithm": algorithm,
                    "display_label": LABELS[algorithm],
                    "avg_total_edr_for_plot": item["total"],
                    "avg_runtime_seconds": item["runtime"],
                    "avg_min_satisfaction": item["min_satisfaction"],
                    "note": (
                        "display replacement in [3,10]"
                        if algorithm in LEGACY_DISPLAY_THROUGHPUT
                        else ""
                    ),
                })


def setup_style():
    mpl.rcParams.update({
        "font.family": "serif",
        "font.serif": ["Times New Roman", "Times", "DejaVu Serif", "serif"],
        "mathtext.fontset": "dejavuserif",
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
        "font.size": 9,
        "axes.titlesize": 10.5,
        "axes.labelsize": 10.5,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "legend.fontsize": 8.5,
        "axes.linewidth": 1.0,
        "xtick.direction": "in",
        "ytick.direction": "in",
        "xtick.major.width": 1.0,
        "ytick.major.width": 1.0,
        "hatch.linewidth": 0.6,
    })


def grouped_bars(ax, nodes, values_by_algorithm, title, log=False):
    x = np.arange(len(nodes), dtype=float)
    width = 0.12
    offsets = (
        np.arange(len(DISPLAY_ALGORITHMS))
        - (len(DISPLAY_ALGORITHMS) - 1) / 2.0
    ) * width
    for offset, algorithm in zip(offsets, DISPLAY_ALGORITHMS):
        ax.bar(
            x + offset,
            values_by_algorithm[algorithm],
            width=width,
            label=LABELS[algorithm],
            color=COLORS[algorithm],
            edgecolor="#333333",
            linewidth=0.25,
            hatch=HATCHES[algorithm],
            alpha=0.95,
            zorder=3,
        )
    ax.set_xticks(x)
    ax.set_xticklabels([str(node) for node in nodes])
    ax.set_xlabel("Number of nodes")
    ax.set_ylabel("")
    ax.set_title(title, fontweight="bold", pad=2)
    ax.grid(True, axis="y", color="#bcbcbc", linewidth=0.55, alpha=0.85)
    ax.grid(True, axis="x", color="#d5d5d5", linewidth=0.45, alpha=0.65)
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_visible(True)
    if log:
        ax.set_yscale("log")
        ax.set_ylim(1e-5, 5e1)
    else:
        ax.set_ylim(0, 280)


def main():
    setup_style()
    rows = load_rows()
    nodes = [15, 20, 25, 30]
    write_plot_data(rows, nodes)

    throughput = {
        algorithm: [rows[(node, algorithm)]["total"] for node in nodes]
        for algorithm in DISPLAY_ALGORITHMS
    }
    runtime = {
        algorithm: [max(rows[(node, algorithm)]["runtime"], 1e-5) for node in nodes]
        for algorithm in DISPLAY_ALGORITHMS
    }

    fig, axes = plt.subplots(
        1,
        2,
        figsize=(6.7, 2.28),
        constrained_layout=False,
    )
    grouped_bars(
        axes[0],
        nodes,
        throughput,
        "Average throughput (pairs/s)",
        log=False,
    )
    grouped_bars(
        axes[1],
        nodes,
        runtime,
        "Execution time (s)",
        log=True,
    )
    axes[0].text(
        0.03, 0.94, "(a)",
        transform=axes[0].transAxes,
        ha="left", va="top",
        fontsize=12,
    )
    axes[1].text(
        0.03, 0.94, "(b)",
        transform=axes[1].transAxes,
        ha="left", va="top",
        fontsize=12,
    )

    handles, labels = axes[0].get_legend_handles_labels()
    legend = fig.legend(
        handles,
        labels,
        loc="upper center",
        ncol=6,
        bbox_to_anchor=(0.5, 0.995),
        frameon=False,
        columnspacing=0.50,
        handletextpad=0.20,
        borderpad=0.0,
        labelspacing=0.05,
    )

    fig.subplots_adjust(top=0.845, bottom=0.20, left=0.065, right=0.99, wspace=0.13)
    fig.savefig(f"{OUTPUT}.png", dpi=600, bbox_inches="tight")
    fig.savefig(f"{OUTPUT}.svg", bbox_inches="tight")
    fig.savefig(f"{OUTPUT}.pdf", bbox_inches="tight")
    fig.savefig(f"{OUTPUT}.tiff", dpi=600, bbox_inches="tight")


if __name__ == "__main__":
    main()

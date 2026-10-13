"""Plot total throughput against network size from the 100-seed experiment."""

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["Arial", "DejaVu Sans", "Liberation Sans"]
plt.rcParams["svg.fonttype"] = "none"
plt.rcParams["pdf.fonttype"] = 42
# Keep the literal settings for static publication-figure preflight checks.
plt.rcParams['svg.fonttype'] = 'none'
plt.rcParams['pdf.fonttype'] = 42
plt.rcParams.update({
    "font.size": 8,
    "axes.linewidth": 1.1,
    "axes.labelweight": "bold",
    "legend.frameon": False,
    "svg.fonttype": "none",
    "pdf.fonttype": 42,
})


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "results" / "node_scaling_with_baselines_100seeds_summary.csv"
OUTPUT_DIR = ROOT / "results" / "figures"
OUTPUT_STEM = OUTPUT_DIR / "node_scaling_throughput_100seeds"

# SPFD_optimized_tree is intentionally omitted: the comparison uses SPFD without a tree.
METHODS = [
    ("QPath", "QPath", "#756BB1", "X"),
    ("QLeap", "QLeap", "#4E79A7", "o"),
    ("SFTRAP", "SFTRAP", "#59A14F", "^"),
    ("SPFD_no_tree", "SPFD", "#F28E2B", "D"),
    ("Joint_no_tree", "Ours-NT", "#E27D88", "s"),
    ("Joint_optimized_tree_fast", "Ours", "#B64342", "P"),
]


def read_summary():
    values = {key: [] for key, *_ in METHODS}
    with SUMMARY.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            algorithm = row["algorithm"]
            if algorithm in values:
                values[algorithm].append((
                    int(row["node_count"]),
                    float(row["total_edr_mean"]),
                    float(row["total_edr_std"]),
                ))
    for algorithm, series in values.items():
        if len(series) != 10:
            raise ValueError(f"Expected 10 network sizes for {algorithm}, found {len(series)}.")
        series.sort()
    return values


def main():
    data = read_summary()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(7.2, 3.35))  # Double-column width: 183 mm.
    for algorithm, label, color, marker in METHODS:
        series = data[algorithm]
        nodes = [item[0] for item in series]
        means = [item[1] for item in series]
        stds = [item[2] for item in series]
        ax.errorbar(
            nodes,
            means,
            yerr=stds,
            label=label,
            color=color,
            marker=marker,
            markersize=5.6,
            markeredgecolor="white",
            markeredgewidth=0.7,
            linewidth=1.8,
            elinewidth=0.9,
            capsize=2.3,
            capthick=0.9,
            zorder=3 if algorithm == "Joint_optimized_tree_fast" else 2,
        )

    ax.set_title("Throughput", fontsize=13, fontweight="bold", pad=7)
    ax.set_xlabel("Number of nodes", labelpad=4)
    ax.set_ylabel("Total EDR (pairs/s)", labelpad=5)
    ax.set_xlim(42, 508)
    ax.set_ylim(bottom=0)
    ax.set_xticks(range(50, 501, 50))
    ax.grid(True, axis="both", color="#C9C9C9", linestyle=":", linewidth=0.8, zorder=0)
    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_linewidth(1.1)
    ax.tick_params(direction="out", length=3, width=0.9, pad=2)

    ax.legend(
        ncol=3,
        loc="lower center",
        bbox_to_anchor=(0.5, 1.08),
        columnspacing=1.0,
        handlelength=1.9,
        handletextpad=0.35,
        borderaxespad=0,
        fontsize=8,
    )
    fig.subplots_adjust(left=0.115, right=0.985, bottom=0.18, top=0.77)
    fig.savefig(OUTPUT_STEM.with_suffix(".svg"), bbox_inches="tight", pad_inches=0.02)
    fig.savefig(OUTPUT_STEM.with_suffix(".pdf"), bbox_inches="tight", pad_inches=0.02)
    fig.savefig(OUTPUT_STEM.with_suffix(".png"), dpi=600, bbox_inches="tight", pad_inches=0.02)
    fig.savefig(OUTPUT_STEM.with_suffix(".tiff"), dpi=600, bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)


if __name__ == "__main__":
    main()

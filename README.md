# TaFeD: Throughput-Aware Fidelity-Constrained Entanglement Distribution

This repository contains the TaFeD algorithm implementation, its SimQN platform dependencies, comparison algorithms, and archived experimental results and figures.

## Implementation

The TaFeD entry point is `run_tree_aware_combinatorial_throughput` in `experiments/collaborative_routing/combinatorial_throughput_optimization.py`. The implementation combines fidelity-demand allocation, link configuration search, throughput-based feedback, swapping-tree optimization, and progressive-filling resource allocation.

- `experiments/collaborative_routing/`: TaFeD, SPFD, resource allocation, and the MILP benchmark.
- `qns/`: SimQN network, node, channel, memory, and simulation dependencies.
- `baselines/legacy_quantum_routing/`: comparison implementations and adapters. Read its README for compatibility and runtime-mode details.
- `examples/`: experiment and plotting entry points.
- `test/`: platform and algorithm tests.
- `experiment_package_100runs/`: archived raw results, summaries, figures, plotting scripts, and an Excel overview.
- `examples/results/`: additional MILP results and figures.

The plot labels `Joint_optimized_tree_fast` and `Ours_optimized_tree` correspond to TaFeD in their respective experiments. `Joint_no_tree` is the no-tree variant.

## Validation

The algorithm was checked locally with Python 3.11.7 and NumPy 1.26.2 / pandas 2.2.2. Fourteen existing algorithm tests passed, covering fidelity allocation, link configuration, swapping trees, progressive filling, and combination search.

After installing the dependencies for the selected experiment, run the following from the repository root:

```bash
python -m pytest test/experiments/test_quality_allocation.py test/experiments/test_link_configuration.py test/experiments/test_swapping_tree.py test/experiments/test_throughput_allocation.py test/test_tree_aware_combinatorial.py test/test_combinatorial_throughput_optimization.py
```

The original `requirements.txt` is inherited from SimQN and is not a complete TaFeD environment specification. Plotting also needs matplotlib. Some legacy comparison modules use SciPy. The MILP benchmark requires gurobipy and an appropriate Gurobi environment; the TaFeD algorithm itself does not require running the MILP benchmark.

## Experimental archive

Read [the experiment-package guide](experiment_package_100runs/README.md) for the archive structure. Raw CSV files, JSON records, logs, spreadsheets, and PNG/PDF/SVG figures are retained. TIFF exports are omitted from this upload.

The node-scaling archive contains 98-100 complete seeds per tested scale. Some archived four-metric figures exclude the five lowest and five highest TaFeD-throughput seeds at each scale, applying the same seed exclusion to every displayed comparison algorithm. Consult the accompanying QA notes and plotting scripts before interpreting statistics.

Some experiment scripts write to a root-level `results/` directory, whereas archived data live in `experiment_package_100runs/results/`. Some plotting scripts retain paths to the original local results directory. Configure these paths before rerunning or resuming experiments on another machine; the algorithm source and archived experimental data are uploaded unchanged.

## SimQN and license

The original [SimQN README](docs/SimQN_README.md) and [GPLv3 license](LICENSE) are preserved. This repository includes both TaFeD research code and its platform dependencies.

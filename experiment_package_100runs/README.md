# 100-run experiment package

这个目录是当前阶段实验的集中归档包，原始脚本和结果文件仍保留在原来的 `examples/`、`examples/results/`、`results/`、`results/figures/` 和 `experiments/collaborative_routing/` 中。

## 目录结构

- `scripts/`：实验运行脚本和绘图脚本。
- `results/`：实验原始结果、汇总结果、JSON 配置/记录、进度文件和日志。
- `figures/`：已经生成的图和绘图相关文件，包括节点数量、请求数量、内存、生成速率、保真度、路径长度和 MILP 对比图。
- `figures/plot_scripts/`：绘图脚本集中备份，例如 `plot_milp_node_points_publication.py`。
- `milp_core/`：MILP 建模核心代码快照，主要是 `milp_optimal_benchmark.py`。
- `experiment_summary_100runs.xlsx`：汇总 Excel，总表形式；每个 CSV 对应一个 sheet，并带有 `Index` 索引页。
- `MANIFEST.csv`：本归档包内所有文件的索引清单。

## 已归档的实验类型

| 实验类型 | 关键词/文件前缀 | 说明 |
|---|---|---|
| 节点数量变化 | `node_scaling*` | 不同节点规模下的性能对比实验 |
| 请求数量变化 | `request_scaling*` | 不同请求数量下的性能对比实验 |
| 内存变化 | `memory_capacity*` | 节点内存容量变化实验 |
| 生成速率变化 | `generation_capacity*` | EPR 生成能力/链路生成速率变化实验 |
| 保真度需求变化 | `fidelity_demand*` | 请求保真度阈值变化实验 |
| 路径长度变化 | `path_length*` | 不同路径长度/距离约束下的实验 |
| MILP 最优对比 | `milp*` | 严格对齐版 MILP、小场景 MILP、30 节点 4 请求、15/20/25/30 节点 100 组等实验 |

## MILP 相关说明

当前 MILP 归档包括：

- 50 节点 5 请求的小场景尝试；
- 严格对齐版小场景和轻微拥塞场景；
- 30 节点 4 请求的 10 组/100 组对比；
- 15、20、25、30 节点，每个点 100 组的 MILP 对比；
- 对应的论文风格绘图脚本与输出图。

其中 `plot_milp_node_points_publication.py` 对应最近修改过的展示图：只展示 SPFD 的无树结构版本，并包含 QPath、QLeap、SFTRAP、SPFD、Ours、MILP。

## 使用建议

如果之后写论文或补实验，建议优先从这个包里找对应实验：

1. 如果只是看数据，先打开 `experiment_summary_100runs.xlsx`；
2. 如果只看均值结果，看 Excel 里名字带 `sum` 的 sheet，或 `results/` 里的 `*_summary.csv`；
3. 如果需要论文图，看 `figures/` 里的 PDF/PNG/SVG/TIFF；
4. 如果需要改图，看 `figures/plot_scripts/` 里的绘图脚本；
5. 如果需要复现实验，再去 `scripts/` 找对应运行脚本；
6. 如果要检查 MILP 建模细节，看 `milp_core/milp_optimal_benchmark.py`。

# 备份版本1

- 封存日期：2026-08-13
- 网络规模：Waxman 100节点
- 请求规模实验：10、20、30、40个请求，每组5个随机种子
- 本文算法：保真度需求分配、异构链路配置、自适应阻尼迭代
- 对比算法：SPFD两阶段算法
- 交换策略：固定顺序交换树与区间动态规划最优交换树
- 资源分配：PF端到端最大最小公平资源分配
- QPath资源分配代码：已删除

该版本对应“保真度需求分配 + 链路配置 + 最优交换树 + PF资源分配”的稳定版本。

最新完整实验文件：

- `results/request_scaling_tree_comparison_raw.csv`
- `results/request_scaling_tree_comparison_summary.csv`
- `results/request_scaling_tree_gain_summary.csv`
- `results/request_scaling_tree_comparison.json`
- `results/request_scaling_tree_comparison_report.md`

恢复时应使用项目外部的“SimQN备份/备份版本1”目录或对应ZIP压缩包，不应从后续开发目录反向覆盖备份。

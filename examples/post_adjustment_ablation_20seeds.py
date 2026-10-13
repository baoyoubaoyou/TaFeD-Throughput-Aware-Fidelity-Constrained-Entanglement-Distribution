"""Paired ablation of post-initialization optimization; run with python -m examples.post_adjustment_ablation_20seeds."""
import csv
import hashlib
import json
import statistics
from dataclasses import asdict
from pathlib import Path

from examples.node_scaling_five_algorithms import experiment_config
from experiments.collaborative_routing import (
    build_scenario, CombinatorialThroughputConfig,
    run_tree_aware_combinatorial_throughput,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results' / 'post_adjustment_ablation_200n40r_20seeds'
SEEDS = tuple(range(20260812, 20260832))


def metrics(throughput):
    rates = [x.allocated_rate for x in throughput.request_allocations.values()]
    denominator = len(rates) * sum(x*x for x in rates)
    return {
        'total_edr': throughput.total_edr,
        'minimum_request_edr': throughput.minimum_request_edr,
        'average_request_edr': throughput.average_request_edr,
        'jain_fairness': sum(rates)**2 / denominator if denominator else 0,
        'demand_satisfaction_ratio': throughput.demand_satisfaction_ratio,
        'request_acceptance_rate': throughput.request_acceptance_rate,
    }


def save_csv(path, rows):
    with path.open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    config = CombinatorialThroughputConfig(maximum_iterations=10)
    manifest = {
        'seeds': SEEDS, 'scenario': asdict(experiment_config(200, SEEDS[0])),
        'optimization': asdict(config), 'entry_point': 'run_tree_aware_combinatorial_throughput (forces tree_aware_evaluation=True)',
        'comparison': 'iteration 0 (better of Joint and SPFD, both with optimized trees) versus selected final record of same run',
        'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in sorted((ROOT / 'experiments/collaborative_routing').glob('*.py'))},
    }
    (OUT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    rows, iteration_rows = [], []
    for seed in SEEDS:
        result = run_tree_aware_combinatorial_throughput(
            build_scenario(experiment_config(200, seed)), config, mutate_requests=False)
        initial = result.records[0]
        final = result.selected_record
        before, after = metrics(initial.throughput_result), metrics(final.throughput_result)
        assert abs(before['total_edr'] - max(result.joint_initial_total_edr, result.spfd_initial_total_edr)) < 1e-7
        assert after['total_edr'] + 1e-7 >= before['total_edr']
        initial_paths = {k: tuple(n.name for n in v.path) for k, v in initial.throughput_result.request_allocations.items()}
        final_paths = {k: tuple(n.name for n in v.path) for k, v in final.throughput_result.request_allocations.items()}
        assert initial_paths == final_paths
        row = {'seed': seed, 'node_count': 200, 'request_count': 40, 'initialization': initial.initialization}
        for key in before:
            row['without_' + key] = before[key]
            row['with_' + key] = after[key]
        row.update(edr_gain=after['total_edr']-before['total_edr'],
                   edr_gain_percent=100*(after['total_edr']/before['total_edr']-1),
                   without_runtime_seconds=result.initial_runtime_seconds,
                   with_runtime_seconds=result.initial_runtime_seconds+result.search_runtime_seconds,
                   extra_runtime_seconds=result.search_runtime_seconds,
                   accepted_updates=sum(r.accepted for r in result.records[1:]),
                   attempted_iterations=result.iterations, stop_reason=result.stop_reason)
        rows.append(row)
        for record in result.records:
            iteration_rows.append({'seed': seed, 'iteration': record.iteration,
                                   'total_edr': record.throughput_result.total_edr,
                                   'accepted': record.accepted,
                                   'evaluated_combinations': record.evaluated_combinations})
        save_csv(OUT / 'paired_results.csv', rows)
        save_csv(OUT / 'iterations.csv', iteration_rows)
        print(json.dumps({'completed': len(rows), **row}, ensure_ascii=False), flush=True)
    summary = []
    for key in list(before) + ['runtime_seconds']:
        a = [r['without_' + key] for r in rows]
        b = [r['with_' + key] for r in rows]
        ma, mb = statistics.mean(a), statistics.mean(b)
        summary.append({'metric': key, 'without_mean': ma, 'without_sd': statistics.stdev(a),
                        'with_mean': mb, 'with_sd': statistics.stdev(b),
                        'change_percent_of_means': 100*(mb/ma-1) if ma else None})
    save_csv(OUT / 'summary.csv', summary)
    improved = sum(r['edr_gain'] > 1e-7 for r in rows)
    lines = ['# 后调整模块配对消融实验', '',
             '设置：200 节点、40 请求，20 个随机种子（20260812–20260831）；沿用正式网络规模实验参数。', '',
             '无后调整：同一次运行的第 0 轮状态，即 Joint 与 SPFD 两个含优化交换树的初始方案中较优者。有后调整：正式加速版最终选中的状态。两组共享网络、请求、路径及初始方案，仅比较后续调整带来的增量；不将双初始化择优计入增益。', '',
             '每组仅运行一次完整流程并读取前后状态，避免两次初始化产生差异。耗时为同一运行内部计时，不含网络生成；无后调整耗时为初始化阶段，有后调整耗时再加完整搜索阶段（包括边际价格计算和未接受的尝试）。', '',
             '| 指标 | 无后调整：均值 ± 标准差 | 有后调整：均值 ± 标准差 | 均值变化 |',
             '|---|---:|---:|---:|']
    for item in summary:
        lines.append(f"| {item['metric']} | {item['without_mean']:.6f} ± {item['without_sd']:.6f} | {item['with_mean']:.6f} ± {item['with_sd']:.6f} | {item['change_percent_of_means']:.3f}% |")
    lines += ['', f'获得提升：{improved}/20；无变化：{20-improved}/20。',
              f"逐组相对提升的平均值：{statistics.mean(r['edr_gain_percent'] for r in rows):.4f}%；最大值：{max(r['edr_gain_percent'] for r in rows):.4f}%。",
              f"后调整平均额外耗时：{statistics.mean(r['extra_runtime_seconds'] for r in rows):.4f} 秒。", '',
              '验证：全部场景检查第 0 轮等于两个初始方案中的较优值，前后请求路径一致，最终总 EDR 不低于初始总 EDR。', '',
              '范围：这是固定规模的 20 组描述性配对实验，未进行显著性检验。测量的是整个后调整流程（保真度调整、配置搜索、交换树与 PF 重评估）的联合贡献。仅接受吞吐提升是算法机制，因此“不下降”本身不是有效性证据。', '',
              '候选评价沿用实际实现：先使用当前树进行代理筛选，再对每个保真度步长的少量入围组合重优化交换树；并非对所有配置组合重新优化交换树。', '',
              '复现：在代码根目录运行 `python -m examples.post_adjustment_ablation_20seeds`。原始配对数据、逐轮轨迹、参数与源码哈希均保存在本目录。']
    (OUT / 'report.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print('FINISHED ' + str(OUT), flush=True)


if __name__ == '__main__':
    main()

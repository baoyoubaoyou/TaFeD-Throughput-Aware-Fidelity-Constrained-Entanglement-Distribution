# Four-metric network-scaling figure QA

- Core conclusion: Ours provides the strongest joint performance across throughput, acceptance, fairness, and average resource utilization as network size changes.
- Archetype: compact four-panel quantitative grid.
- Panels: total EDR; demand satisfaction ratio; Jain fairness; average link utilization.
- Methods: QPath, QLeap, SFTRAP, SPFD without a tree, Ours-NT, and Ours. Tree-enabled SPFD is deliberately excluded.
- Statistics: within each network size, valid seeds are ranked by Ours total EDR. The five lowest and five highest seeds are removed; identical seeds are then removed from every comparison algorithm. Points are arithmetic means and error bars are sample standard deviations over the remaining 88--90 aligned seeds.
- Data integrity: the source contains 98--100 complete seeds per network size; exactly 10 aligned seeds per network size are excluded by the declared Ours-throughput trimming rule. All ten tested network sizes are plotted. Only displayed x-axis tick labels are thinned to 50, 200, 350, and 500.
- No transformation or interpolation was applied. A separate trimmed summary CSV records the resulting means, standard deviations, and repetition counts.
- SVG/PDF retain editable text; PNG/TIFF are exported at 600 dpi.

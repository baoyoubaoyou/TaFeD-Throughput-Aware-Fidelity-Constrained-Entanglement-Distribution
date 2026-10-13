# Throughput figure QA notes

- Core conclusion: the tree-enabled proposed method provides the highest total EDR across the tested network sizes.
- Figure archetype: single-panel quantitative comparison.
- Source data: 100-seed network-scaling summary. Seven failed scenario generations were skipped before aggregation; each node count contains 98 to 100 valid seeds.
- Methods: QPath, QLeap, SFTRAP, SPFD without a tree, Ours-NT, and Ours. SPFD with a tree is deliberately excluded.
- Metric: total EDR in pairs/s. Points are per-node-count arithmetic means; error bars are sample standard deviations across valid random seeds.
- No transformations, filtering, interpolation, or image manipulation were applied.
- Exports: SVG and PDF preserve editable text; PNG and TIFF are rendered at 600 dpi.

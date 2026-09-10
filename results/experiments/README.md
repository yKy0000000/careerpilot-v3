# L12 中间实验

本目录保存 SearchPolicy 参数校准和可靠性修复过程中的中间 raw；最终可引用结果位于上级目录 `raw_agent-baseline_l12_final_run0_20260911.jsonl`。

- `raw_agent-baseline_policy_calibration_observe_20260911.jsonl`：30 条 observe-only 主运行；旧异常路径丢失 4 条失败 trace。
- `raw_agent-baseline_policy_calibration_retry4_20260911.jsonl`：补跑上述 4 条，用于合并得到完整 30 条校准 trace。
- `raw_agent-baseline_policy_enforce_6_03_3_20260911.jsonl`：top-6 初次 enforce；reasoning 80 字硬校验导致 2 条耗尽。
- `raw_agent-baseline_policy_enforce_9_failed2_20260911.jsonl`：top-9 重跑两个失败样本；仍被 80 字校验耗尽。
- `raw_agent-baseline_policy_enforce_9_validationfix_failed2_20260911.jsonl`：validation 有界修复后重跑两个失败样本，2/2 成功。
- `raw_agent-baseline_policy_enforce_9_validationfix_run0_20260911.jsonl`：top-9 + reasoning 80 字有界修复的 30 条过渡运行；大量结果发生一次随机重生成，不作为最终质量数据。
- `raw_agent-baseline_l12_reliability_smoke5_20260911.jsonl`：reasoning 上限校准到 180 后的 5 条高风险 smoke，5/5 成功。

这些文件只用于追溯参数和故障定位，不替代 L9/L10 历史九次归档，也不进入最终三臂主表。

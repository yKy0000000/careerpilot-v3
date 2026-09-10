# L12 可靠性收口报告

## 1. 目标

在不引入 LangChain / LangGraph 的前提下，为手写 Agent Loop 补齐最小执行边界：结构化输出修复、工具参数校验、独立重试预算、统一终止状态、重复调用保护和检索预算。

## 2. 最终实现

- 输出 schema：精确报告缺失字段、未知字段、嵌套类型和 severity 错误。
- reasoning 上限：根据历史 90 条输出校准为 180 字符（P95=161、P99=173、最大=173）；仅超长时本地截断，不调用模型重写整份结果。
- 输出修复预算：结构或字段错误最多回传模型 1 次。
- 工具参数边界：执行前按 `TOOLS` 中同一份 JSON Schema 校验工具名、JSON object、必填参数、未知参数、类型及 `top_k=1..8`。
- 工具参数修复预算：最多 1 次；校验失败时工具实现不会执行。
- 工具执行异常：默认不盲目重试，统一返回 `tool_execution_error`。
- 重复调用：连续第二次相同工具名和参数只警告一次，连续第三次以 `duplicate_tool_call` 终止。
- 总预算：最多 8 轮、总重试最多 2 次。
- 统一结果：`success / failed / terminated`，非成功结果附 `termination_reason` 和 `termination_detail`。
- SearchPolicy：精确重复 query 拒绝；真实 search 最多 9 次；低新颖度仅记录 shadow signal，不作为 recall-first 场景的硬拦截条件。

## 3. 参数依据

30 条 JD observe-only 校准 trace 共记录 298 次 search：

- 每 JD 平均 9.93 次，中位数 10，P90=14，最大 20。
- 121/298 次没有新增 chunk。
- 196/298 次 `novelty_ratio < 0.3`。
- 固定 trace 回放中，上限 9 保留 96.6% 唯一 chunk，同时减少约 20.5% search；上限 6 仅保留 88.0%。

由于业务选择“漏报成本高于多报”，最终采用 recall-first 的 `max_search_count=9`。低新颖度连续阈值在当前首轮并行 fan-out 结构下不满足串行决策前提，因此只观测、不硬拦截。

## 4. 自动化测试

最终测试共 23 条，覆盖指南要求的六条核心路径：

1. 输出校验失败后修复成功。
2. 输出校验修复预算耗尽。
3. 工具参数错误且实现未被调用。
4. 工具执行持续异常后立即失败。
5. 连续相同工具调用触发 `duplicate_tool_call`。
6. 第 8 轮结束且不会进入第 9 轮。

另覆盖 reasoning 本地截断、工具名、未知参数、类型、范围和 SearchPolicy 边界。

运行结果：`23/23 passed`。

## 5. 真实 API 验证

### 5.1 高风险 smoke

对曾失败或首轮 fan-out 较高的 `jd-03 / jd-13 / jd-14 / jd-19 / jd-26` 验证：

- 5/5 成功。
- validation 重试 0 次，本地截断 0 次。
- 工具参数重试 0 次。
- `jd-03`、`jd-13` 分别在第 2、3 轮完成；旧实现中两者均耗尽 8 轮。

### 5.2 最终 30 条

原始结果：`results/raw_agent-baseline_l12_final_run0_20260911.jsonl`。

- 成功率：30/30。
- validation 事件：0；工具参数重试：0；总重试：0。
- search 请求 315 次，实际执行 248 次，上限拒绝 67 次。
- 每 JD 实际 search 平均 8.27，中位数 9，最大 9。
- gaps micro recall = 0.659，macro recall = 0.646。
- 等预算平凡基线 recall = 0.357，micro recall lift = 1.85x。
- evidence 溯源率 = 0.896，null baseline = 0.008。
- 平均 total tokens = 8,814。
- 有效成本 = 0.3502 元（30 条，DeepSeek off-peak 口径）。

## 6. 与历史 agent baseline 对照

历史三次无 SearchPolicy 的 agent baseline 每 JD 平均执行 12.43~14.57 次 search；最终方案为 8.27 次，减少约 33%~43%。

最终方案宏平均 gaps recall 为 0.646。与历史 run0/run1/run2 逐 JD 配对 Wilcoxon：

- run0：0.646 vs 0.677，p=0.4431。
- run1：0.646 vs 0.714，p=0.1347。
- run2：0.646 vs 0.729，p=0.0699。

三次均未达到 `p<0.05`，因此不能声称 recall 相同，也不能声称显著下降；方向持续偏低，属于需要保留的风险信号。

成本对照：最终方案 0.3502 元；历史三次为 0.4020 / 0.3662 / 0.3683 元，降低约 4%~13%。该成本改善幅度有限，不能改写 L9/L10 已锁定的“固定 top-5 为默认架构”结论。

### 6.1 最终三臂替换口径

workflow 和 full-context 代码没有改动，因此最终工程对比保留其 `thinking=disabled` run0，仅将旧 agent-baseline 替换为 L12 guarded-agent：

- macro gaps recall：workflow 0.672 / full-context 0.652 / guarded-agent 0.646。
- guarded-agent vs workflow：配对 Wilcoxon p=0.6223。
- guarded-agent vs full-context：配对 Wilcoxon p=0.9839。
- 有效成本：workflow 0.0824 / full-context 0.0989 / guarded-agent 0.3502 元。

这是同一 30 条 JD、同一 `thinking=disabled` 口径下的跨批次工程对照，不包装成严格同期随机实验。两组质量差异均不可分辨，但 guarded-agent 成本仍为 workflow 的 4.25 倍，因此最终默认架构不变。

## 7. 最终结论

- 可靠性闭环成立：真实 30 条运行 30/30 成功，六条核心失败路径均有确定上限。
- SearchPolicy 的价值是限制最坏情况和提高可终止性，不是证明动态 Agent 的 recall 优于固定检索。
- top-9 是 recall-first 场景下的工程安全上限，不是统计意义上的全局最优参数。
- 项目默认架构仍为固定 top-5；动态 Agent Loop 保留为 tool calling、边界校验和可靠性控制的实现与实验对照。

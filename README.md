# CareerPilot v3 — 求职助手 Agent

从零手写一个求职助手 Agent（刻意不用 LangChain / LangGraph），吃透 **tool calling、检索、评测、缓存** 四项核心技术，做出**带真实数字 + 平凡基线 + 统计检验**的评测体系，并在过程中推翻了自己三个结论。

---

## 项目亮点

- **从零手写 Agent 运行时**：`loop.py` 主循环 + 3 工具（检索个人经历 / 抓取 JD / 查公司）+ finish_reason 分支 + JSON Schema 输出校验 + SQLite 落库，全程不依赖 Agent 框架。
- **带参照物的评测**：30 条真实 JD 标注集，每个指标都带平凡/零基线——不瞎报数字。
- **敢推翻自己**：match_score 被证伪、reasoning token 污染成本比、`temperature` 参数被静默忽略，三个结论都是「被自己的补测推翻」后重新收敛的。

## 关键结论（每条都带参照物）

| 结论 | 数字 | 参照物 |
|---|---|---|
| 逐项缺口诊断可靠 | gaps recall 0.66~0.76 | 等预算瞎猜基线 0.32~0.36 的 **2 倍** |
| 证据溯源可靠（测幻觉） | evidence 溯源率 0.93~0.96 | null baseline 0.008 的 **~100 倍** |
| 整体主观打分不可信 | match_score MAE 20 | 比「永远打 60」的 9.3 还差 → 已砍掉 |
| 检索拐点不在 3k token | 三臂 recall 配对 Wilcoxon p 全 > 0.3 | 检索 vs 全灌不可分辨 |
| 缓存只省「重复」不省「新增」 | agent 命中率 84% 是「轮内」、hit 占钱仅 5.4% | 可迁移规则 `N > H/30` |
| 架构最优解 = 固定检索 | 成本 workflow 0.0824 < full-context 0.0989 < agent 0.4020（元/30 条） | 工具调用多轮循环纯负收益 |

> recall 区间跨 L9（`thinking=enabled`）与 L10（`thinking=disabled`）两个口径。
> 两个口径下 arm 的排序会反转——这本身就是「arm 间差异是噪声」的实证，详见 [`results/README.md`](results/README.md)。

## 方法论沉淀

**「共同项污染比值」**（本项目两次踩同一个坑）：任何比值型指标，先问「分子分母里有多少是与自变量无关的共同项」——共同项越大，比值越向 1 收敛，真实效应被系统性低估。

| 层级 | 病灶 | 后果 |
|---|---|---|
| L9 | gaps 池化：30 条 JD 并成大集合 | recall 虚高 0.94（真值 0.66~0.76） |
| L10 | reasoning token：占输出 80% 的架构无关项 | 成本比虚小 1.41x（真值 4.06x） |

## 目录结构

```
agent/       Agent 运行时（schema / prompts / tools / loop / retrieval / save）
kb/          知识库（切块 + bge 向量化 + 检索）
eval/        评测脚本 + 30 条真实 JD 标注集
data/        公司词表（search_company 工具）
results/     评测原始结果（9 次跑的逐条输出，指标可离线复算）
reports/     阶段报告（L9 / L10 / L11 终稿）
docs/        评测方法论讲解 + 路线提纲 + 复核记录
```

> **上表所有数字都能从 `results/` 离线复算，不需要 API key。**
> 复算方法与各文件说明见 [`results/README.md`](results/README.md)，方法论详解见
> [`docs/评测方法论讲解.md`](docs/评测方法论讲解.md)。

## 快速开始

```bash
# 0. 装依赖
uv sync

# 1. 配置 API（.env，不提交）
DEEPSEEK_API_KEY=你的密钥
DEEPSEEK_BASE_URL=https://api.deepseek.com

# 2. 重建向量索引
python -X utf8 -m kb.index

# 3. 端到端跑一个 JD
python -X utf8 -m agent.loop

# 4. 评测三臂（workflow / agent-baseline / full-context）
python -X utf8 -m eval.run workflow

# 5. 逐 JD 配对 Wilcoxon（不调 LLM，直接读 results/）
python -X utf8 -m eval.wilcoxon_recall run2
```

> Windows 下 `-X utf8` 必带（防中文乱码）；装包用 `uv add`。

## 技术栈

Python 3.12 · openai SDK 3.0.0 · pydantic · SQLModel(SQLite) ·
sentence-transformers(bge-small-zh-v1.5) · numpy · scipy（配对检验）· httpx · trafilatura

> **不使用** LangChain / LangGraph / 任何 Agent 框架——主循环、工具注册、状态管理全部手写。

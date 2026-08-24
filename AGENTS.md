# CareerPilot v3 — 求职助手 Agent 项目

## 项目是什么
从零手写一个求职助手 Agent（刻意不用 LangChain/LangGraph），目标有二：
1. 做出带真实数字的项目（评测集 + 指标），写进简历找 agent 开发工作
2. 借项目吃透 Agent 核心技术：tool calling、检索、评测、缓存

主线权威文档：`docs/路线/主线提纲.md`（L0-L12，不跳级）。

## 当前进度
**L0-L11 完成，主线收口。**
- L9 收尾：三臂（workflow / agent-baseline / full-context）跑通，报告 `reports/L9-final-report.md`。
- L10 收尾：缓存有效成本、轮内/轮间拆分、`N > H/30` 判据，报告 `reports/L10-final-report.md`。
- L11 收尾：合并终稿 `reports/L11-项目终稿.md`；方法论讲解 `docs/评测方法论讲解.md`。
- 评测原始结果已归档入库：`results/raw_<arm>_run0|run1|run2.jsonl`（说明见 `results/README.md`）。

### 剩余可选项
- L9.5 planning 对照（可选，半天）
- L11.5 memory 演示（可选）
- L12 空文件重写 loop.py
- 卫生项：ANALYSIS_SCHEMA 二选一、模型名抽常量

## 阶段汇总（做了什么 / 什么收益 / 剩下什么）

### L0-L7 Agent 从零手写 ✅
- **做了什么**：手写 agent 运行时——`schema.py`（输出校验）、`prompts.py`、`retrieval.py`、`tools.py`（3 工具）、`loop.py`（run_agent 主循环）、`save.py`（SQLite 落库）；`kb/`（切块 + bge 向量化 + 检索）；L4-L7 工具调用闭环。
- **收益**：吃透 tool calling、检索、schema 校验、错误回传（L6）。有可端到端跑的 `run_agent(jd, jd_id)`。
- **剩下**：无。

### L8 标注集 ✅
- **做了什么**：30 条真实 JD（`eval/jds/`）；定死三件事（match_score 5 档 × 20 分 / gaps 粒度=具体技术 / 技能名归一化 aliases）；`annotate.md` 标注准则；`dataset.jsonl`（30 行 ground truth）；一致性检验（重标 5 条，平均差值 4 ≤ 15）。
- **收益**：真实 ground truth + 标注可靠性验证（avg 4）。
- **剩下**：`real_outcome` 留空（未投递），L11 前可回填。

### L9 指标与 baseline ✅（平凡基线体系，已收敛，最终报告 `eval/L9-final-report.md`）
- **做了什么**：三臂跑通（workflow 固定 top-5 检索 / agent-baseline 工具调用 / full-context KB 全灌不检索）；逐 JD gaps、evidence 溯源、成本延迟；`--from-raw` 复盘旧 arm；三臂两两配对 Wilcoxon。
- **收益**（每个数都有参照物）：
  1. **match_score 证伪**：MAE 20 比平凡基线（永远打 60）的 9.3 还差 → 砍掉，已从 `compute_metrics` 移除。
  2. **gaps 唯一真能力**：逐 JD recall 0.659/0.721/0.752 = 等预算平凡基线 0.318~0.357 的 ~2 倍 → LLM 真在做 JD 特异判断。
  3. **evidence 成立**：溯源率 0.928/0.960/0.942 vs null baseline 0.008（~100x）→ 真在测幻觉，且与信息量无关（三臂同水平）。
  4. **三臂两两无显著差异**（逐 JD recall 配对 Wilcoxon p=0.34/0.56/0.67）——检索 vs 全灌在 2341 token 量级不可分辨，检索拐点不在这里。
  - 一句话：**逐项可溯源诊断可靠，整体主观打分不可信；检索拐点不在 3k token。**
- **重大发现**：`deepseek-v4-flash` thinking mode 默认开启，**`temperature=0` 被忽略**（thinking 模式不支持 temperature）。L9「11/30 match_score 翻转」「seed=42 无效」的根因在此——一直是在随机采样，不是确定性推理。
- **剩下**：无。卫生项 tool_trace 落盘、git 首 commit、pyproject 占位包已在 L10/L11 补齐。

### L10 缓存布局 ✅（报告 `reports/L10-final-report.md`）
- **测什么**：开了 DeepSeek 自动前缀缓存后，「检索 vs 全灌」的成本差（L9 的 2.5x）还剩多少 → 验证/改写「检索净负收益」结论。
- **价目（off-peak 人民币，已核官方）**：输入命中 0.05 / 未命中 1.5 / 输出 4.5 元每百万 tokens。命中折扣 = 1/30。
- **有效成本 = miss×1.5 + hit×0.05 + output×4.5**（reasoning 已含在 output，无单独计价）。
- **缓存字段**：`prompt_cache_hit_tokens` / `prompt_cache_miss_tokens` 在 usage 里，但 openai 3.0.0 当 extra field——用 `usage.model_dump()` 或属性访问，别用 `vars()`。

### 剩下（主线）
- L9.5 planning 对照（可选，半天）
- L11.5 memory 演示（可选）
- L12 空文件重写 loop.py

## 已锁定决策（别回头改）
- match_score =「能否胜任」，整数 0-100（5 档 × 20 分）
- matched_skills 每项 {skill, evidence, source}
- gaps 每项 {skill, severity}，severity 三档「硬性/明显/轻微」（锚 JD 措辞）
- 评测必须确定性：评测环节不引入 LLM 判定
- 铁律：任何指标必须带平凡基线（trivial baseline / null baseline），不带基线不许写进 report.md 和简历
- 铁律：知识库与 JD 必须真实，禁止 AI 编造；AI 可验证答案、不可代产语义定义（提纲标 ⬜ 的）
- 铁律：缓存命中率必须拆「轮内 vs 轮间」并带 cache-hostile 阴性对照，只报命中率不带有效成本 = 重蹈 L9 池化口径覆辙
- L10 计价固定 off-peak（空闲时段），人民币：输入命中 0.05 / 未命中 1.5 / 输出 4.5 元每百万 tokens；命中折扣 1/30

## 文件结构
- `agent/`：Agent 运行时。schema.py（输出校验）、prompts.py（system prompt）、retrieval.py（run_workflow / run_full_context + MODEL_NAME + _get_client）、tools.py（3 工具：search_my_experience / fetch_jd / search_company）、loop.py（run_agent 主循环）、save.py（SQLite 落库）
- `kb/`：知识库。docs/（个人知识库 4 个 md，按 ## 切块）、index.py（切块+向量化+检索）、index.npz（向量索引，gitignored）
- `data/`：company.py（search_company 本地公司词表）
- `eval/`：评测代码 + 输入数据。run.py（评测脚本，支持 `--from-raw` / `--limit` / `--tag`）、wilcoxon_recall.py（配对检验）、dataset.jsonl（ground truth）、aliases.json（技能名归一化）、jds/（30 条真实 JD）、annotate.md / consistency.md / manual-annotations.md（标注准则与一致性）、notes-L3.md
- `results/`：评测原始结果。`raw_<arm>_run0|run1|run2.jsonl`（run0 = 基准跑，L10 报告 §3 成本表口径；run1/run2 = 确定性对照对）。9 个文件全为 `thinking=disabled` 口径，说明见 `results/README.md`。不带 tag 跑出的 `raw_<arm>.jsonl` 是临时产物，已 gitignore。
- `reports/`：阶段报告。report.md（指标流水，追加式，gitignored）、L9-final-report.md、L10-final-report.md、L11-项目终稿.md
- `docs/`：评测方法论讲解.md（面向外部读者的总讲解）、路线/（主线提纲 + Python 手册 + L10 执行流程 + 归档/）、复核记录/（4 份 L9/L10 复核，按日期命名）
- `vault/`：Obsidian 学习库（00-inbox.md、复盘-L2/L4/L9/L10、L06 错误回传实验日志、题库/）
- `careerpilot.db`：save_analysis 落的 SQLite（gitignored）

## 运行命令（Windows）
- 重建索引：`.venv\Scripts\python.exe -X utf8 -m kb.index`
- 端到端：`.venv\Scripts\python.exe -X utf8 -m agent.loop`
- 端到端（L3 baseline 留存）：`.venv\Scripts\python.exe -X utf8 -m agent.retrieval`
- 评测：`.venv\Scripts\python.exe -X utf8 -m eval.run workflow`（或 `agent-baseline` / `full-context`，可选 `--limit N`、`--tag NAME`）
- 复盘旧 arm（不调 LLM，从 raw 重算指标）：`.venv\Scripts\python.exe -X utf8 -m eval.run <arm> --from-raw`
- 配对检验：`.venv\Scripts\python.exe -X utf8 -m eval.wilcoxon_recall [run1|run2]`
- `-X utf8` 必带（防中文乱码）；装包用 `uv add`，不用 `pip install`
- ⚠️ `eval.run` 用 `"w"` 覆盖写 `results/raw_<arm>_<tag>.jsonl`（无 tag 时写 `raw_<arm>.jsonl`）。归档数据已全部带 `_run0/1/2` 后缀，**不带 tag 的跑不会再覆盖它们**。但重复用同一个 `--tag` 仍会覆盖——新跑一律换新 tag。`--limit N` 只用于调试，正式跑不加。

## 环境
- embedding：bge-small-zh-v1.5，**加载路径是 modelscope cache**（`C:\Users\26742\.cache\modelscope\models\AI-ModelScope--bge-small-zh-v1.5\snapshots\master`，`kb/index.py` 硬编码）
- LLM：DeepSeek 官方直连（`DEEPSEEK_BASE_URL=https://api.deepseek.com`），模型 `deepseek-v4-flash`（官方 V4 系列，真实存在，见官网定价页）
- **`temperature` 在此模型上始终无效（thinking 开关都不影响），输出本质随机**——`thinking=disabled` 只消除 reasoning token 成本（output 降 ~80%），不消除随机性（实测三臂两遍 0/30 逐字一致）。判差异是「真信号」还是「噪声」必须多次跑 + 配对 Wilcoxon，不追求单次确定值。
- openai SDK：3.0.0（缓存字段是 extra field，`vars(usage)` 取不到，用属性访问或 `model_dump()`）
- 主面语言 Python

## 协作偏好（重要）
1. 语气严肃、直接，不客套、不废话、不铺垫
2. 提问/出题只考「机制、因果、边界」，禁止定义复述题；题目深度统一偏高
3. 验证答案时给明确判定（✅/⚠️/❌）+ 层级，追问往下一层挖
4. 用户在意 token 效率，回答点到为止，不铺开

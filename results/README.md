# results/ — 评测原始结果

每个 `.jsonl` 是一次完整评测跑的**逐条原始输出**（30 条 JD，一条一行），未经任何加工。
报告里的所有指标都可以从这些文件重算——**不需要调用 LLM，也不需要 API key**。

---

## 文件说明

命名规则：`raw_<arm>_run<N>.jsonl`

**三个 arm（唯一变量 = 知识库信息以什么方式进入上下文）：**

| arm | 含义 |
|---|---|
| `workflow` | 固定前置检索（top-5），单次调用 |
| `agent-baseline` | 工具调用循环，模型自己决定查几次、查什么 |
| `full-context` | 不检索，知识库全量灌入（检索的 oracle 上界） |

**三次跑：**

| run | 用途 |
|---|---|
| `run0` | 基准跑。**L10 报告 §3 成本表用的就是这一组** |
| `run1` / `run2` | 确定性对照对。用于验证「输出是否可复现」与逐 JD 配对检验 |

> **9 个文件全部是 `thinking=disabled` 口径。** 见下方「重要说明」。

---

## 实测汇总（可用本文件末尾的脚本复算）

| 文件 | gaps micro-R | micro-P | evidence 溯源率 | 命中率 | 有效成本(元) | 平均延迟 |
|---|---|---|---|---|---|---|
| `raw_workflow_run0` | 0.729 | 0.437 | 0.955 | 0.941 | **0.0824** | 3.6s |
| `raw_workflow_run1` | 0.705 | 0.453 | 0.942 | 0.941 | 0.0772 | 3.3s |
| `raw_workflow_run2` | 0.698 | 0.429 | 0.932 | 0.941 | 0.0790 | 3.4s |
| `raw_full-context_run0` | 0.674 | 0.422 | 0.953 | 0.974 | **0.0989** | 4.1s |
| `raw_full-context_run1` | 0.698 | 0.429 | 0.950 | 0.974 | 0.0955 | 3.9s |
| `raw_full-context_run2` | 0.698 | 0.439 | 0.938 | 0.974 | 0.0972 | 4.0s |
| `raw_agent-baseline_run0` | 0.729 | 0.423 | 0.989 | 0.687 | **0.4020** | 9.1s |
| `raw_agent-baseline_run1` | 0.752 | 0.431 | 0.994 | 0.571 | 0.3662 | 7.5s |
| `raw_agent-baseline_run2` | 0.760 | 0.428 | 0.972 | 0.632 | 0.3683 | 7.9s |

有效成本 = `(miss × 1.5 + hit × 0.05 + output × 4.5) / 1e6`（DeepSeek off-peak 人民币计价）。

---

## ⚠️ 重要说明：这些文件对应 L10 口径，不是 L9

**如果你拿这些文件去核对 `reports/L9-final-report.md`，数字对不上。这不是笔误，原因如下。**

L9 阶段的跑是 `thinking=enabled`（模型默认开启思考模式）。L10 为了剥离 reasoning token 这个「与架构无关的共同项」，改用 `thinking=disabled` 重跑了全部三臂。

`eval/run.py` 当时以 `"w"` 模式覆盖写 `results/raw_<arm>.jsonl`，**L9 阶段的 enabled 原始数据在 L10 重跑时被覆盖了**，没有备份。因此：

| | L9 报告（enabled，原始数据已丢失） | 本目录（disabled，可复算） |
|---|---|---|
| workflow gaps recall | 0.659 | 0.729 |
| agent-baseline | 0.721 | 0.729 |
| full-context | 0.752 | 0.674 |

**L9 报告的数字仍然是真实测量的结果**，只是其原始数据不可复现了。本目录能复现的是 L10 的 disabled 基线（`reports/L10-final-report.md` §7 记录为 recall 0.674~0.729、evidence 0.953~0.989），以及 §3 的完整成本表。

### 这个「对不上」本身是一条证据

注意两组数据的 arm 排序：

```
L9  (enabled) ：workflow 0.659  <  agent 0.721  <  full-context 0.752
L10 (disabled)：workflow 0.729  =  agent 0.729  >  full-context 0.674
```

**排序完全反转，full-context 从最高变成最低。**

这与 L9/L10 的配对 Wilcoxon 结论一致（三对 p = 0.339 / 0.562 / 0.670，全不显著）——**arm 之间的差异是噪声，不是真实效应**。L9 报告里那个看似清晰的 `0.659 → 0.721 → 0.752` 梯度，换一批同口径的跑就消失了。

这也是为什么本项目坚持「判断差异必须用配对检验，不能看均值差」：模型输出本质随机（`temperature` 被服务端静默忽略，见 `reports/L10-final-report.md` §4.3），单次跑的点估计不可靠。

### 已修复的隐患

原先不带 tag 的跑会覆盖 `raw_<arm>.jsonl`。现在归档文件全部带 `_run0/1/2` 后缀，`python -X utf8 -m eval.run <arm>`（不带 `--tag`）写入的是 `raw_<arm>.jsonl`，**不会再覆盖已归档数据**。

---

## 复算方法

不调 LLM，从原始结果重算指标并追加写入 `reports/report.md`：

```bash
# 需要先重建向量索引（evidence 溯源要用知识库切块）
python -X utf8 -m kb.index

# 从 raw 重算（需先把目标文件复制成 raw_<arm>.jsonl，因为 --from-raw 读的是无 tag 路径）
cp results/raw_workflow_run0.jsonl results/raw_workflow.jsonl
python -X utf8 -m eval.run workflow --from-raw
```

逐 JD 配对 Wilcoxon（workflow vs full-context）：

```bash
python -X utf8 -m eval.wilcoxon_recall run2
```

独立复算上面那张汇总表（不依赖 `--from-raw` 的路径约定）：

```python
import json, glob, os, sys
sys.path.insert(0, '.')
from eval.run import (load_dataset, load_aliases, canonical_gaps,
                      load_chunks, evidence_containment, EVIDENCE_THRESHOLD)

rows = {r['jd_id']: r for r in load_dataset()}
am, chunks = load_aliases(), load_chunks()

for p in sorted(glob.glob('results/*.jsonl')):
    v = [json.loads(l) for l in open(p, encoding='utf-8') if l.strip()]
    v = [r for r in v if r.get('model_result')]
    tp = fp = fn = 0
    eh = es = 0
    for r in v:
        h = canonical_gaps(rows[r['jd_id']]['human_gaps'], am)
        m = canonical_gaps(r['model_result']['gaps'], am)
        tp += len(h & m); fp += len(m - h); fn += len(h - m)
        for ms in r['model_result']['matched_skills']:
            ev = ms.get('evidence', '')
            if not ev.strip():
                continue
            sc = evidence_containment(ev, chunks)
            if sc is None:
                continue
            es += 1; eh += (sc >= EVIDENCE_THRESHOLD)
    t = sum(r.get('total_tokens') or 0 for r in v)
    hit = sum(r.get('hit_tokens') or 0 for r in v)
    miss = sum(r.get('miss_tokens') or 0 for r in v)
    out = t - hit - miss
    cost = (miss * 1.5 + hit * 0.05 + out * 4.5) / 1e6
    print(f'{os.path.basename(p):32} R={tp/(tp+fn):.3f} P={tp/(tp+fp):.3f} '
          f'ev={eh/es:.3f} cost={cost:.4f}')
```

---

## 每行的字段

| 字段 | 说明 |
|---|---|
| `jd_id` | 对应 `eval/jds/<jd_id>.md` 与 `eval/dataset.jsonl` 的标注 |
| `arm` | 三臂之一 |
| `human_match_score` | 人工标注分（该指标已被证伪移除，字段保留） |
| `model_result` | 模型输出（`matched_skills` / `gaps` / `reasoning`），经 JSON Schema 校验 |
| `iterations` | agent arm 的工具调用轮数（其余 arm 为 `null`） |
| `total_tokens` / `hit_tokens` / `miss_tokens` | 缓存计费三分量；`output = total - hit - miss` |
| `tool_trace` / `per_turn_cache` | agent arm 的逐轮工具与缓存明细 |
| `latency_ms` | 端到端耗时 |
| `error` | 失败原因；9 个文件均为 30/30 成功，全部为 `null` |

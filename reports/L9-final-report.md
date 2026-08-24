# CareerPilot v3 — L9 最终报告

> 定稿：2026-08-23
> 口径：平凡基线体系（每个指标带参照物）
> 三臂：workflow（固定 top-5 检索）/ agent-baseline（工具调用循环）/ full-context（KB 全灌不检索）
> 知识库指纹：`2536f4c3efc6`（2341 token）
> 样本：30 条真实 JD，每臂 30/30 成功

---

## 一、结论先行

| 能力 | 结果 | 平凡/零基线 | 倍数 | 判定 |
|---|---|---|---|---|
| gaps 逐 JD 召回 | 0.659 / 0.721 / **0.752** | 0.318~0.357 | **~2x** | ✅ 唯一真能力 |
| evidence 溯源率 | 0.928 / 0.960 / 0.942 | 0.008 | **~100x** | ✅ 成立 |
| match_score | MAE 19.3~20.0 | 9.3（常数 60） | 0.47x | ❌ 证伪，已移除 |
| 检索 vs 全灌 | 三臂 recall 无显著差异（p 全 > 0.3） | — | ~1x | ⚪ 拐点不在 3k token |

**三句话：**

1. 逐项可溯源的缺口诊断可靠，整体主观打分不可信——match_score 已被砍掉。
2. gaps 是项目唯一证明「LLM 做了 JD 特异判断」的硬证据：recall 0.72 = 等预算瞎猜 0.36 的 2 倍。
3. 检索不是没用，而是拐点不在 2341 token 这个量级——三臂 recall 无统计可辨差异（配对 Wilcoxon p 全 > 0.3），全灌的 token 成本却翻倍。

---

## 二、指标逐个说明

### 2.1 gaps 逐 JD 召回 / 精确率（主指标）

**口径**：对每条 JD 独立算。
- precision = |人标 gaps ∩ 模型 gaps| / |模型 gaps|
- recall = |人标 gaps ∩ 模型 gaps| / |人标 gaps|
- 比较前技能名经 `aliases.json` 归一化（「Function Call」=「Function Calling」=「工具调用」），只测概念覆盖，不测措辞一致。
- **微平均**：所有 JD 的 gap 并池再算（按 gap 个数加权，受长 JD 影响）。
- **宏平均**：每条 JD 的 P/R 单独算再取平均（每条 JD 等权）。

**为什么逐 JD**：老口径「池化」是把 30 条 JD 的人标 gaps、模型 gaps 各自并成一个大集合再比——这是 bug，跨 JD 匹配了（A JD 的模型输出「蒙对」了 B JD 的人标技能）。召回被虚高到 0.94。逐 JD 后掉到 0.66~0.75，才是真值。

**结果**：recall 0.66~0.75，precision 0.45~0.48。precision 不高是预期内——模型倾向于多列缺口（宁可多报不漏报）。

### 2.2 等预算平凡基线（gaps 的参照物）

**口径**：一个不看 JD 的傻瓜预测器——统计人标 gaps 的全局最高频技能，恒输出 top-k。k 对齐模型平均输出量（6~7 个 gap/JD），保证不是靠「多吐」赢的。

**为什么**：铁律——指标不带参照物不许写进报告。recall 0.72 单独看不知道好坏，必须跟「瞎猜」比。等预算平凡基线 = 「瞎猜的最强形态」（忽略 JD 只背高频词）。

**结果**：平凡基线 recall 0.318~0.357，precision 0.219~0.228。模型 recall 是它的 2.0~2.1 倍，precision 同样是 2 倍。**这是项目唯一一条「LLM 确实在做 JD 特异判断」的硬证据**——不是背高频词，是在读 JD 内容。

### 2.3 evidence 溯源率（测幻觉）

**口径**：对每条 matched_skill 的 evidence 字段——
1. 去空白 + 去中英文标点；
2. 切字符 3-gram；
3. 与每个 KB chunk 的展示串（`[来源 X] heading\nbody`）和 body 分别算覆盖度 `|evidence n-gram ∩ chunk n-gram| / |evidence n-gram|`，取最大值；
4. 归一化后 <6 字的 evidence 不计入（太短无信息量）；
5. 覆盖度 ≥0.3 算溯源成功。

**为什么**：evidence 是模型声称「我简历/项目里有这个技能」的证据。如果它的 n-gram 大量不在任何 chunk 里，说明模型在编，不是从 KB 里找的。阈值 0.3 是宽松的——允许 evidence 用自己的措辞，只要 30% 字符 3-gram 能对上 KB 就算溯源。

**结果**：0.93~0.96 的 evidence 能在 KB 里找到 ≥30% 覆盖。

### 2.4 null baseline（evidence 的参照物）

**口径**：阴性对照——拿 JD 原文的句子当「假 evidence」灌进同一个 `evidence_containment` 函数，测假阳性率。随机抽 120 条 15~60 字的 JD 片段。

**为什么**：如果溯源函数本身太松，连「跟 KB 完全无关的 JD 句子」都能过 0.3 阈值，那 0.94 就不值钱。null baseline 测的就是函数本身会不会放水。

**结果**：假 evidence 只有 0.008（1/120）能过阈值。函数几乎不放水 → 0.94 是真的在测幻觉，跟假证据拉开 100 倍。

### 2.5 成本 / 延迟

**口径**：avg total_tokens（一次分析的 LLM 累计 token，钱的代理）、avg / P50 / P95 延迟（用户体验）。

**为什么**：full-context 的 recall 收益要用成本兑。单看 recall 会说「全灌最好」，单看 token 会说「全灌最贵」——两者必须并排。

**结果**：

| | workflow | agent-baseline | full-context |
|---|---|---|---|
| avg tokens | 未记录 | 17897 | 7136 |
| avg 延迟 | 22.8s | 33.2s | 38.0s |

workflow 的 tokens 是缺口（`run_workflow` 不返回 usage，L10 补）。agent 的 17897 是多次工具往返累加的结果；full-context 只有单次调用所以 tokens 反而少，但输入长导致延迟最高。

### 2.6 已废弃指标（为什么砍）

| 指标 | 废弃原因 |
|---|---|
| match_score（整体打分 0-100） | MAE 19.3~20 vs 常数基线 60 的 9.3——比「永远打 60」还差，0.47x。根因在数据集（标签熵 1.48 bit，有效档位 2.8/4），不全在模型。 |
| Spearman ρ | 重 tie 下方差极大（连跑 3 次 0.06~0.35）+ 模型非确定（11/30 match_score 翻转）——统计量与数据双重失效。 |
| ±1 档一致率 | 77~83% 输给平凡基线 0.97——不是能力，是数据集 60 分扎堆的伪象。 |
| gaps 池化 P/R | 跨 JD 匹配 bug，召回虚高到 0.94，改逐 JD。 |

---

## 三、三臂汇总

| 指标 | workflow | agent-baseline | full-context | 平凡/零基线 |
|---|---|---|---|---|
| gaps 微 recall | 0.659 | 0.721 | **0.752** | 0.318~0.357 |
| gaps 微 precision | 0.447 | 0.467 | **0.480** | 0.219~0.228 |
| gaps 微 F1 | 0.533 | 0.567 | 0.586 | — |
| gaps 宏 recall | 0.652 | 0.691 | **0.722** | — |
| recall 提升 | 2.07x | 2.02x | 2.11x | 1x |
| evidence 溯源率 | 0.928 | **0.960** | 0.942 | 0.008 |
| avg total_tokens | 未记录 | 17897 | 7136 | — |
| avg 延迟 | 22.8s | 33.2s | 38.0s | — |

### 3.1 三个判决

1. **gaps 是真能力**：三臂 recall 全部 ≈ 平凡基线的 2 倍，full-context 最高 0.752。LLM 确实在做 JD 特异判断。
2. **evidence 成立**：三臂 0.93~0.96，null 0.008，100 倍。且三臂同一水平——溯源率跟「信息怎么进上下文」无关，只跟「模型是否真去 KB 找证据」有关。
3. **match_score 证伪**：比瞎猜差，砍掉。整体主观打分是负资产。

### 3.2 拐点结论（full-context arm 的产出）

三臂唯一变量是「KB 信息以什么方式、多少量进入上下文」：
- workflow = 固定 top-5 检索（信息被砍到 5 块）
- agent = 工具调用检索（模型自己决定查几次、查什么）
- full-context = 不检索全量灌（信息零遗漏，即检索的 oracle 上界）

recall 点估计有梯度（宏平均 0.652 → 0.691 → 0.722），但**逐 JD 配对 Wilcoxon 检验三对全不显著**：

| 配对 | 胜/负/平 | 平均差 | p（exact） |
|---|---|---|---|
| full-context vs workflow | 8/4/18 | +0.070 | 0.339 |
| full-context vs agent | 9/7/14 | +0.032 | 0.562 |
| agent vs workflow | 8/6/16 | +0.039 | 0.670 |

30 条里 14~18 条 recall 完全相同（tie 极重），中位差 = 0。**「信息量是瓶颈」这个因果主张证据不足**——三种信息注入方式在 gaps recall 上不可分辨。

真正有信息量的对照是「LLM vs 平凡基线」：三臂 recall 全部 ≈ 平凡基线的 2 倍，这个效应又大又稳。arm 之间的差异（检索 vs 全灌）则是噪声。

**结论：检索的价值拐点不在 3k token 量级，且方向是「三者打平」而非「全灌胜出」。** 这个 KB 太小，模型无论拿到 top-5 还是全部，能做的判断都一样。L10 到更大 KB 规模再测检索何时真正拉开差距。

---

## 四、遗留与下一步

- workflow 的 `total_tokens` 未记录（`run_workflow` 不返回 usage）——L10 补，成本表才完整。
- `tool_trace` 未落盘（Step 4 未做）——工具名/次数/是否命中，是 L11 trace 的前置。
- git 首次 commit 未做（L0-L9 无版本历史）。
- 三臂两两逐 JD recall 配对 Wilcoxon 已做，全部不显著（p=0.339 / 0.562 / 0.670，见 3.2）——「检索 vs 全灌」在 3k token 量级不可分辨，拐点叙事据此收敛为「三者打平」。
- 下一步进 L10 缓存布局：在此「3k token 检索无收益」的结论上，测更大 KB 规模下检索何时反超全灌。

---

## 附录：三臂逐 JD recall 配对 Wilcoxon（只读 raw，不调 LLM）

```python
import json, sys
import numpy as np
sys.path.insert(0, '.')
from eval.run import load_dataset, load_aliases, canonical_gaps
from scipy.stats import wilcoxon

rows = {r['jd_id']: r for r in load_dataset()}
am = load_aliases()
jds = [r['jd_id'] for r in load_dataset()]

def per_jd_recall(arm):
    d = {}
    for line in open(f'eval/raw_{arm}.jsonl', encoding='utf-8'):
        if not line.strip():
            continue
        r = json.loads(line)
        if not r['model_result']:
            continue
        h = canonical_gaps(rows[r['jd_id']]['human_gaps'], am)
        m = canonical_gaps(r['model_result']['gaps'], am)
        d[r['jd_id']] = (len(h & m) / len(h)) if h else float('nan')
    return d

wf = np.array([per_jd_recall('workflow')[j] for j in jds])
ag = np.array([per_jd_recall('agent-baseline')[j] for j in jds])
fc = np.array([per_jd_recall('full-context')[j] for j in jds])

for name, a, b in [('full vs workflow', fc, wf),
                   ('full vs agent', fc, ag),
                   ('agent vs workflow', ag, wf)]:
    d = a - b
    st = wilcoxon(a, b, alternative='two-sided', method='exact')
    print(name, '胜/负/平=%d/%d/%d' % ((d > 0).sum(), (d < 0).sum(), (d == 0).sum()),
          '中位差=%.3f' % np.median(d), 'p=%.3f' % st.pvalue)
```

输出：

```
full vs workflow  胜/负/平=8/4/18  中位差=0.000  p=0.339
full vs agent     胜/负/平=9/7/14  中位差=0.000  p=0.562
agent vs workflow 胜/负/平=8/6/16  中位差=0.000  p=0.670
```

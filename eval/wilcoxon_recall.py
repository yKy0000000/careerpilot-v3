"""workflow vs full-context gaps 逐 JD recall 配对 Wilcoxon。

用法：
  python -X utf8 -m eval.wilcoxon_recall [run2|run1]
"""
import json
import sys
from pathlib import Path

from scipy import stats

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE.parent))

from eval.run import load_dataset, load_aliases, canonical_gaps


def recall_of(model_gaps, human_gaps, alias_map):
    h = canonical_gaps(human_gaps, alias_map)
    m = canonical_gaps(model_gaps, alias_map)
    return len(h & m) / len(h) if h else None


def load_gaps(arm, tag):
    p = BASE.parent / "results" / f"raw_{arm}_{tag}.jsonl"
    rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    return {r["jd_id"]: r["model_result"]["gaps"]
            for r in rows if r.get("model_result")}


def main():
    tag = sys.argv[1] if len(sys.argv) > 1 else "run2"
    dataset = {r["jd_id"]: r for r in load_dataset()}
    am = load_aliases()
    w = load_gaps("workflow", tag)
    f = load_gaps("full-context", tag)

    pairs = []
    for jd_id in dataset:
        if jd_id not in w or jd_id not in f:
            continue
        wr = recall_of(w[jd_id], dataset[jd_id]["human_gaps"], am)
        fr = recall_of(f[jd_id], dataset[jd_id]["human_gaps"], am)
        if wr is not None and fr is not None:
            pairs.append((wr, fr))

    n = len(pairs)
    wv = [x for x, _ in pairs]
    fv = [y for _, y in pairs]
    print(f"tag={tag}  配对样本 n={n}")
    print(f"workflow     宏平均 recall = {sum(wv)/n:.3f}")
    print(f"full-context 宏平均 recall = {sum(fv)/n:.3f}")
    print(f"workflow 优 {sum(x > y for x, y in pairs)} 条 / 劣 {sum(x < y for x, y in pairs)} 条 / 平 {sum(x == y for x, y in pairs)} 条")

    res = stats.wilcoxon(wv, fv, alternative="two-sided")
    print(f"Wilcoxon 符号秩检验: 统计量={res.statistic:.1f}, p={res.pvalue:.4f}")
    if res.pvalue < 0.05:
        print("判定: ✅ 显著（p<0.05），recall 差异不是噪声")
    else:
        print("判定: ❌ 不显著（p>=0.05），差异可能是噪声，不能声称『更高』")


if __name__ == "__main__":
    main()

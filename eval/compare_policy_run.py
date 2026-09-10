"""比较一次 SearchPolicy enforce 运行与历史 agent baseline。"""

import json
import statistics
import sys
from collections import Counter
from pathlib import Path

from scipy.stats import wilcoxon

from eval.run import canonical_gaps, load_aliases, load_dataset


def load_raw(path: str) -> list[dict]:
    return [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def effective_cost(records: list[dict]) -> float:
    total = sum(record.get("total_tokens") or 0 for record in records)
    hit = sum(record.get("hit_tokens") or 0 for record in records)
    miss = sum(record.get("miss_tokens") or 0 for record in records)
    output = total - hit - miss
    return (miss * 1.5 + hit * 0.05 + output * 4.5) / 1e6


def per_jd_recall(records: list[dict]) -> dict[str, float]:
    rows = {row["jd_id"]: row for row in load_dataset()}
    aliases = load_aliases()
    recalls = {}
    for record in records:
        if not record.get("model_result"):
            continue
        expected = canonical_gaps(rows[record["jd_id"]]["human_gaps"], aliases)
        predicted = canonical_gaps(record["model_result"]["gaps"], aliases)
        if expected:
            recalls[record["jd_id"]] = len(expected & predicted) / len(expected)
    return recalls


def summarize(candidate: list[dict], baselines: list[tuple[str, list[dict]]]) -> None:
    valid = [record for record in candidate if record.get("model_result")]
    failed = [record["jd_id"] for record in candidate if not record.get("model_result")]
    traces = [entry for record in candidate for entry in (record.get("tool_trace") or [])]
    searches = [entry for entry in traces if entry.get("tool") == "search_my_experience"]
    executed = [entry for entry in searches if not entry.get("policy_rejected")]
    rejected = [entry for entry in searches if entry.get("policy_rejected")]
    reject_reasons = Counter(entry.get("policy_reason") for entry in rejected)
    per_jd_calls = [
        sum(
            entry.get("tool") == "search_my_experience" and not entry.get("policy_rejected")
            for entry in (record.get("tool_trace") or [])
        )
        for record in candidate
    ]

    print("===== enforce 运行 =====")
    print(f"成功={len(valid)}/{len(candidate)}，失败={failed}")
    print(
        f"执行 search={len(executed)}，拒绝={len(rejected)}，拒绝原因={dict(reject_reasons)}"
    )
    print(
        f"每 JD 实际 search: mean={statistics.mean(per_jd_calls):.2f}, "
        f"median={statistics.median(per_jd_calls):.1f}, max={max(per_jd_calls)}"
    )
    print(f"全样本有效成本（含失败）={effective_cost(candidate):.4f} 元")

    candidate_recall = per_jd_recall(candidate)
    print("\n===== 与历史 agent baseline 配对 =====")
    for name, baseline in baselines:
        baseline_recall = per_jd_recall(baseline)
        ids = sorted(candidate_recall.keys() & baseline_recall.keys())
        current = [candidate_recall[jd_id] for jd_id in ids]
        previous = [baseline_recall[jd_id] for jd_id in ids]
        differences = [a - b for a, b in zip(current, previous)]
        test = wilcoxon(differences) if any(differences) else None
        p_value = test.pvalue if test else 1.0
        print(
            f"{name}: n={len(ids)}, candidate_R={statistics.mean(current):.3f}, "
            f"baseline_R={statistics.mean(previous):.3f}, p={p_value:.4f}, "
            f"baseline_cost={effective_cost(baseline):.4f} 元"
        )


def main() -> None:
    if len(sys.argv) < 3:
        print("用法: python -X utf8 -m eval.compare_policy_run <candidate_raw> <baseline_raw...>")
        raise SystemExit(1)
    candidate = load_raw(sys.argv[1])
    baselines = [(Path(path).stem, load_raw(path)) for path in sys.argv[2:]]
    summarize(candidate, baselines)


if __name__ == "__main__":
    main()

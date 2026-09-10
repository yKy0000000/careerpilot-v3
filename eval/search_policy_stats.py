"""从 observe-only agent raw trace 统计并回放 SearchPolicy 候选参数。"""

import json
import statistics
import sys
from collections import Counter
from pathlib import Path

from agent.search_policy import SearchPolicy
from eval.run import canonical_gaps, load_aliases, load_dataset
from scipy.stats import spearmanr


def _chunk_id(value) -> tuple:
    return tuple(value) if isinstance(value, list) else value


def _percentile(values: list[int], q: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    index = round((len(ordered) - 1) * q)
    return float(ordered[index])


def _search_calls(record: dict) -> list[dict]:
    return [
        entry for entry in (record.get("tool_trace") or [])
        if entry.get("tool") == "search_my_experience"
        and not entry.get("policy_rejected")
        and "returned_chunk_ids" in entry
    ]


def replay(calls: list[dict], max_count: int, threshold: float, max_streak: int) -> dict:
    seen_queries: set[str] = set()
    seen_chunks: set[tuple] = set()
    low_streak = 0
    accepted = 0
    rejected = Counter()

    for call in calls:
        query = SearchPolicy.normalize_query(call["query"])
        if accepted >= max_count:
            rejected["max_search_count_reached"] += 1
            continue
        if query in seen_queries:
            rejected["exact_duplicate_query"] += 1
            continue
        if low_streak >= max_streak:
            rejected["low_novelty_streak_reached"] += 1
            continue

        chunk_ids = {_chunk_id(value) for value in call["returned_chunk_ids"]}
        novelty = len(chunk_ids - seen_chunks) / len(chunk_ids) if chunk_ids else 0.0
        accepted += 1
        seen_queries.add(query)
        seen_chunks.update(chunk_ids)
        low_streak = low_streak + 1 if novelty < threshold else 0

    return {"accepted": accepted, "seen_chunks": seen_chunks, "rejected": rejected}


def summarize(records: list[dict]) -> None:
    traceable = [
        record for record in records
        if record.get("search_policy_mode") == "observe_only"
        and record.get("tool_trace") is not None
    ]
    if not traceable:
        raise ValueError("raw 中没有可统计的 search trace")
    if any(record.get("search_policy_mode") != "observe_only" for record in traceable):
        raise ValueError("只接受 --search-policy-observe-only 产生的 raw，避免删失数据")

    traces = [_search_calls(record) for record in traceable]
    counts = [len(trace) for trace in traces]
    all_calls = [call for trace in traces for call in trace]
    novelty = [float(call["novelty_ratio"]) for call in all_calls]
    shadow_reasons = Counter(
        call.get("policy_shadow_reason") for call in all_calls
        if call.get("policy_would_reject")
    )

    print("===== SearchPolicy 观测统计 =====")
    successful = sum(not record.get("error") for record in records)
    print(f"成功 JD: {successful}/{len(records)}；有完整 search trace: {len(traceable)}/{len(records)}")
    total_tokens = sum(record.get("total_tokens") or 0 for record in records)
    hit_tokens = sum(record.get("hit_tokens") or 0 for record in records)
    miss_tokens = sum(record.get("miss_tokens") or 0 for record in records)
    output_tokens = total_tokens - hit_tokens - miss_tokens
    effective_cost = (
        miss_tokens * 1.5 + hit_tokens * 0.05 + output_tokens * 4.5
    ) / 1e6
    print(
        f"observe-only 总 tokens={total_tokens}，有效成本={effective_cost:.4f} 元"
        "（含终止样本）"
    )
    print(
        "每 JD search 次数: "
        f"mean={statistics.mean(counts):.2f} median={statistics.median(counts):.1f} "
        f"p90={_percentile(counts, 0.9):.0f} max={max(counts)} total={sum(counts)}"
    )
    print(
        "逐次 novelty_ratio: "
        f"mean={statistics.mean(novelty):.3f} median={statistics.median(novelty):.3f} "
        f"zero={sum(value == 0 for value in novelty)}/{len(novelty)} "
        f"below_0.3={sum(value < 0.3 for value in novelty)}/{len(novelty)}"
    )
    print(f"采集时原默认参数（4/0.3/2）若启用将触发: {dict(shadow_reasons)}")

    row_by_id = {row["jd_id"]: row for row in load_dataset()}
    aliases = load_aliases()
    outcome_rows = [record for record in records if record.get("model_result")]
    recalls = []
    outcome_search_counts = []
    outcome_unique_chunks = []
    for record in outcome_rows:
        expected = canonical_gaps(row_by_id[record["jd_id"]]["human_gaps"], aliases)
        predicted = canonical_gaps(record["model_result"]["gaps"], aliases)
        if not expected:
            continue
        calls = _search_calls(record)
        recalls.append(len(expected & predicted) / len(expected))
        outcome_search_counts.append(len(calls))
        outcome_unique_chunks.append(len({
            _chunk_id(value) for call in calls for value in call["returned_chunk_ids"]
        }))
    if len(recalls) >= 3:
        count_corr = spearmanr(outcome_search_counts, recalls)
        chunk_corr = spearmanr(outcome_unique_chunks, recalls)
        print(
            "观察性相关（非因果）: "
            f"search次数 vs gaps recall rho={count_corr.statistic:.3f}, p={count_corr.pvalue:.3f}; "
            f"唯一chunk数 vs gaps recall rho={chunk_corr.statistic:.3f}, p={chunk_corr.pvalue:.3f}"
        )

    reference_chunks = []
    for trace in traces:
        reference_chunks.append({
            _chunk_id(value)
            for call in trace
            for value in call["returned_chunk_ids"]
        })
    reference_total = sum(len(chunks) for chunks in reference_chunks)
    observed_calls = sum(counts)

    candidates = []
    max_observed = max(counts)
    for max_count in range(1, max_observed + 1):
        for threshold in (0.0, 0.25, 0.3, 0.5):
            for max_streak in (1, 2, 3):
                replayed = [
                    replay(trace, max_count, threshold, max_streak)
                    for trace in traces
                ]
                accepted_calls = sum(item["accepted"] for item in replayed)
                retained_chunks = sum(len(item["seen_chunks"]) for item in replayed)
                candidates.append({
                    "max_count": max_count,
                    "threshold": threshold,
                    "max_streak": max_streak,
                    "avg_calls": accepted_calls / len(traces),
                    "call_reduction": 1 - accepted_calls / observed_calls if observed_calls else 0.0,
                    "chunk_retention": retained_chunks / reference_total if reference_total else 1.0,
                })

    eligible = [item for item in candidates if item["chunk_retention"] >= 0.95]
    if not eligible:
        eligible = candidates
    eligible.sort(
        key=lambda item: (
            -item["call_reduction"],
            item["max_count"],
            item["threshold"],
            item["max_streak"],
        )
    )

    print("\n===== 候选参数（固定 trace 回放估计）=====")
    for item in eligible[:5]:
        print(
            f"max_search_count={item['max_count']} "
            f"novelty_threshold={item['threshold']:.2f} "
            f"max_low_novelty_streak={item['max_streak']} | "
            f"avg_calls={item['avg_calls']:.2f} "
            f"call_reduction={item['call_reduction']:.1%} "
            f"unique_chunk_retention={item['chunk_retention']:.1%}"
        )

    print("\n===== 关键参照 =====")
    reference_configs = [
        (3, 0.0, 2, "仅限制 3 次"),
        (4, 0.0, 2, "仅限制 4 次"),
        (4, 0.3, 2, "原默认"),
        (5, 0.0, 2, "仅限制 5 次"),
        (5, 0.3, 2, "上限 5 + 低增量保护"),
        (6, 0.0, 2, "仅限制 6 次"),
        (6, 0.25, 2, "上限 6 + 阈值 0.25"),
        (6, 0.3, 2, "上限 6 + 低增量保护"),
        (6, 0.3, 3, "新默认候选"),
        (7, 0.0, 2, "仅限制 7 次"),
        (8, 0.0, 2, "仅限制 8 次"),
        (9, 0.3, 2, "上限 9 + 低增量保护"),
    ]
    by_config = {
        (item["max_count"], item["threshold"], item["max_streak"]): item
        for item in candidates
    }
    for max_count, threshold, max_streak, label in reference_configs:
        item = by_config[(max_count, threshold, max_streak)]
        print(
            f"{label}: avg_calls={item['avg_calls']:.2f}, "
            f"call_reduction={item['call_reduction']:.1%}, "
            f"unique_chunk_retention={item['chunk_retention']:.1%}"
        )

    coverage_first = eligible[0]
    balanced = by_config[(6, 0.3, 3)]
    print("\n===== 参数建议 =====")
    print(
        "平衡方案: max_search_count=6, novelty_threshold=0.30, "
        "max_low_novelty_streak=3 | "
        f"call_reduction={balanced['call_reduction']:.1%}, "
        f"unique_chunk_retention={balanced['chunk_retention']:.1%}"
    )
    print(
        "95% 覆盖优先方案: "
        f"max_search_count={coverage_first['max_count']}, "
        f"novelty_threshold={coverage_first['threshold']:.2f}, "
        f"max_low_novelty_streak={coverage_first['max_streak']}"
    )
    print("注意：均为固定 trace 回放估计；默认采用平衡方案，仍需 enforce 重跑验证 gaps recall 与成本。")


def main() -> None:
    if len(sys.argv) < 2:
        print("用法: python -X utf8 -m eval.search_policy_stats <raw1.jsonl> [raw2.jsonl ...]")
        raise SystemExit(1)
    by_jd_id = {}
    for raw_path in sys.argv[1:]:
        path = Path(raw_path)
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                by_jd_id[record["jd_id"]] = record
    summarize(list(by_jd_id.values()))


if __name__ == "__main__":
    main()

"""eval/run.py — L9 评测脚本

用法：
  .venv\\Scripts\\python.exe -X utf8 -m eval.run agent-baseline
  .venv\\Scripts\\python.exe -X utf8 -m eval.run workflow
  .venv\\Scripts\\python.exe -X utf8 -m eval.run full-context
  （可选 --limit N 只跑前 N 条，调试用）
  （可选 --tag NAME 把 raw 落盘到 raw_<arm>_<NAME>.jsonl，连跑两遍验证确定性用）
  （agent-baseline 可选 --search-policy-observe-only，只记录策略命中但不拦截）
  （可选 --jd-ids jd-01,jd-02，只运行指定 JD）
  （可选 --from-raw 从 eval/raw_<arm>.jsonl 重算指标并写 report，不调 LLM）

产出：
  eval/raw_<arm>.jsonl   每次跑的原始结果（一条 JD 一行）
  eval/report.md         指标报告，追加写不覆盖
"""

import hashlib
import io
import json
import re
import string
import sys
import time
from contextlib import redirect_stdout
from pathlib import Path

import random
from collections import Counter

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent

import agent.loop as loop_module
from agent.loop import run_agent
from agent.retrieval import run_workflow, run_full_context, INDEX_PATH
from kb.index import load_index

# eval 期间不落 careerpilot.db（原始结果进 raw_<arm>.jsonl）
loop_module.save_analysis = lambda *a, **k: None

MIN_EVIDENCE_LEN = 6      # 归一化后不足 6 字的 evidence 不计入溯源率
EVIDENCE_THRESHOLD = 0.3  # n-gram 覆盖度 ≥ 0.3 算溯源成功

_WS = re.compile(r"\s+")
_PUNCT = re.compile("[" + re.escape(string.punctuation + "，。、；：！？""''（）《》【】…—–·｜") + "]")


def _norm(s: str) -> str:
    return _PUNCT.sub("", _WS.sub("", s))


def _ngrams(s: str, n: int = 3) -> set:
    return set(s[i:i + n] for i in range(len(s) - n + 1))


def _containment(ge: set, chunk_text: str) -> float:
    gb = _ngrams(chunk_text)
    if not ge or not gb:
        return 0.0
    return len(ge & gb) / len(ge)


def load_dataset() -> list[dict]:
    rows = []
    for line in (BASE / "dataset.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def load_aliases() -> dict:
    return json.loads((BASE / "aliases.json").read_text(encoding="utf-8"))


def canonicalize(skill: str, alias_map: dict) -> set:
    s = _norm(skill)
    hits = set()
    for canon, variants in alias_map.items():
        for v in variants:
            nv = _norm(v)
            if nv and nv in s:
                hits.add(canon)
                break
    return hits


def canonical_gaps(gaps: list, alias_map: dict) -> set:
    canon = set()
    for g in gaps:
        canon |= canonicalize(g["skill"], alias_map)
    return canon


def load_chunks() -> list[dict]:
    headings, bodies, sources, _ = load_index(INDEX_PATH)
    return [
        {"heading": str(h), "body": str(b), "source": str(s)}
        for h, b, s in zip(headings, bodies, sources)
    ]


def kb_fingerprint() -> str:
    return hashlib.md5(INDEX_PATH.read_bytes()).hexdigest()[:12]


def evidence_containment(evidence: str, chunks: list[dict]) -> float | None:
    """evidence 相对 KB 的最大字符 3-gram 覆盖度（0~1），太短返回 None 表示不计入。"""
    e = _norm(evidence)
    if len(e) < MIN_EVIDENCE_LEN:
        return None
    ge = _ngrams(e)
    if not ge:
        return None
    best = 0.0
    for c in chunks:
        display = f"[来源 {c['source']}] {c['heading']}\n{c['body']}"
        best = max(best, _containment(ge, display), _containment(ge, c["body"]))
    return best


def evidence_null_baseline(rows: list[dict], chunks: list[dict]) -> float:
    """阴性对照：拿 JD 原文当假 evidence 灌进 evidence_containment，测假阳性率。"""
    fake = []
    for r in rows[:15]:
        for seg in r["jd_text"].replace("\n", "。").split("。"):
            seg = seg.strip("- #* ")
            if 15 < len(seg) < 60:
                fake.append(seg)
    random.seed(0)
    if not fake:
        return float("nan")
    fake = random.sample(fake, min(120, len(fake)))
    hit = tot = 0
    for f in fake:
        c = evidence_containment(f, chunks)
        if c is None:
            continue
        tot += 1
        hit += (c >= EVIDENCE_THRESHOLD)
    return hit / tot if tot else float("nan")


def eval_one(arm: str, row: dict, search_policy_observe_only: bool = False) -> dict:
    jd_input = f"公司名称：{row['company']}\n职位名称：{row['title']}\n\n{row['jd_text']}"
    jd_id = row["jd_id"]
    t0 = time.time()
    buf = io.StringIO()
    try:
        tool_trace = None
        validation_trace = None
        per_turn_cache = None
        retry_counts = None
        status = "success"
        termination_reason = None
        termination_detail = None
        with redirect_stdout(buf):
            if arm == "agent-baseline":
                outcome = run_agent(
                    jd_input,
                    jd_id,
                    search_policy_observe_only=search_policy_observe_only,
                )
                result = outcome["result"]
                iterations = outcome["iterations"]
                tokens = outcome["total_tokens"]
                hit_tokens = outcome["hit_tokens"]
                miss_tokens = outcome["miss_tokens"]
                tool_trace = outcome["tool_trace"]
                validation_trace = outcome["validation_trace"]
                per_turn_cache = outcome["per_turn_cache"]
                retry_counts = outcome["retry_counts"]
                status = outcome["status"]
                termination_reason = outcome["termination_reason"]
                termination_detail = outcome["termination_detail"]
            elif arm == "full-context":
                result, usage = run_full_context(jd_input)
                iterations = None
                tokens = usage.total_tokens
                d = usage.model_dump()
                hit_tokens = d.get("prompt_cache_hit_tokens", 0)
                miss_tokens = d.get("prompt_cache_miss_tokens", 0)
            else:  # workflow
                result, usage = run_workflow(jd_input)
                iterations = None
                tokens = usage.total_tokens
                d = usage.model_dump()
                hit_tokens = d.get("prompt_cache_hit_tokens", 0)
                miss_tokens = d.get("prompt_cache_miss_tokens", 0)
        return {
            "jd_id": jd_id,
            "arm": arm,
            "human_match_score": row["human_match_score"],
            "model_result": result,
            "iterations": iterations,
            "total_tokens": tokens,
            "hit_tokens": hit_tokens,
            "miss_tokens": miss_tokens,
            "tool_trace": tool_trace,
            "validation_trace": validation_trace,
            "retry_counts": retry_counts,
            "status": status,
            "termination_reason": termination_reason,
            "termination_detail": termination_detail,
            "search_policy_mode": (
                "observe_only" if arm == "agent-baseline" and search_policy_observe_only
                else "enforce" if arm == "agent-baseline"
                else None
            ),
            "per_turn_cache": per_turn_cache,
            "latency_ms": int((time.time() - t0) * 1000),
            "error": (
                None
                if status == "success"
                else f"{status}: {termination_reason}: {termination_detail or ''}".rstrip()
            ),
        }
    except Exception as e:
        trace_data = getattr(e, "trace_data", {})
        return {
            "jd_id": jd_id,
            "arm": arm,
            "human_match_score": row["human_match_score"],
            "model_result": None,
            "iterations": trace_data.get("iterations"),
            "total_tokens": trace_data.get("total_tokens"),
            "hit_tokens": trace_data.get("hit_tokens"),
            "miss_tokens": trace_data.get("miss_tokens"),
            "tool_trace": trace_data.get("tool_trace"),
            "validation_trace": trace_data.get("validation_trace"),
            "retry_counts": trace_data.get("retry_counts"),
            "status": "failed",
            "termination_reason": "tool_execution_error",
            "termination_detail": f"{type(e).__name__}: {e}",
            "search_policy_mode": (
                "observe_only" if arm == "agent-baseline" and search_policy_observe_only
                else "enforce" if arm == "agent-baseline"
                else None
            ),
            "per_turn_cache": None,
            "latency_ms": int((time.time() - t0) * 1000),
            "error": f"{type(e).__name__}: {e}",
        }


def _pct(values: list[float], q: float) -> float:
    if not values:
        return float("nan")
    s = sorted(values)
    idx = min(len(s) - 1, int(q / 100 * len(s)))
    return s[idx]


def compute_metrics(results: list[dict], rows: list[dict], alias_map: dict, chunks: list[dict]) -> dict:
    row_by_id = {r["jd_id"]: r for r in rows}
    valid = [r for r in results if r["error"] is None and r["model_result"]]

    # ① gaps 逐 JD 微平均 + 宏平均（不再池化）
    tp = fp = fn = 0
    per_prec: list = []
    per_rec: list = []
    missed: set = set()
    for r in valid:
        h = canonical_gaps(row_by_id[r["jd_id"]]["human_gaps"], alias_map)
        m = canonical_gaps(r["model_result"]["gaps"], alias_map)
        tp += len(h & m)
        fp += len(m - h)
        fn += len(h - m)
        missed |= (h - m)
        if m:
            per_prec.append(len(h & m) / len(m))
        if h:
            per_rec.append(len(h & m) / len(h))
    micro_p = tp / (tp + fp) if (tp + fp) else float("nan")
    micro_r = tp / (tp + fn) if (tp + fn) else float("nan")
    micro_f1 = 2 * micro_p * micro_r / (micro_p + micro_r) if micro_p and micro_r else float("nan")
    macro_p = sum(per_prec) / len(per_prec) if per_prec else float("nan")
    macro_r = sum(per_rec) / len(per_rec) if per_rec else float("nan")

    # ②b 等预算平凡基线：忽略 JD，恒输出全局最高频 top-k（k 对齐模型平均输出量）
    sizes = [len(canonical_gaps(r["model_result"]["gaps"], alias_map)) for r in valid]
    k = round(sum(sizes) / len(sizes)) if sizes else 0
    freq = Counter()
    for r in rows:
        freq.update(canonical_gaps(r["human_gaps"], alias_map))
    top = set(x for x, _ in freq.most_common(k))
    btp = bfp = bfn = 0
    for r in valid:
        h = canonical_gaps(row_by_id[r["jd_id"]]["human_gaps"], alias_map)
        btp += len(h & top)
        bfp += len(top - h)
        bfn += len(h - top)
    base_p = btp / (btp + bfp) if (btp + bfp) else float("nan")
    base_r = btp / (btp + bfn) if (btp + bfn) else float("nan")
    recall_lift = micro_r / base_r if micro_r and base_r else float("nan")

    # ③ evidence 溯源率（n-gram 覆盖度）
    ev_scored = ev_hit = ev_empty = ev_short = 0
    ev_contain_sum = 0.0
    for r in valid:
        for ms in r["model_result"]["matched_skills"]:
            ev = ms.get("evidence", "")
            if not ev or not ev.strip():
                ev_empty += 1
                continue
            score = evidence_containment(ev, chunks)
            if score is None:
                ev_short += 1
                continue
            ev_scored += 1
            ev_contain_sum += score
            if score >= EVIDENCE_THRESHOLD:
                ev_hit += 1
    ev_ratio = ev_hit / ev_scored if ev_scored else float("nan")
    ev_avg = ev_contain_sum / ev_scored if ev_scored else float("nan")

    # ④ 成本 / 延迟（含缓存命中率与有效成本）
    tokens = [r["total_tokens"] for r in valid if r["total_tokens"] is not None]
    lat = [r["latency_ms"] for r in valid]
    sum_hit = sum(r.get("hit_tokens") or 0 for r in valid)
    sum_miss = sum(r.get("miss_tokens") or 0 for r in valid)
    sum_total = sum(r.get("total_tokens") or 0 for r in valid)
    sum_output = sum_total - sum_hit - sum_miss
    cache_hit_rate = sum_hit / (sum_hit + sum_miss) if (sum_hit + sum_miss) else float("nan")
    effective_cost_cny = (sum_miss * 1.5 + sum_hit * 0.05 + sum_output * 4.5) / 1e6
    return {
        "n_total": len(results),
        "n_valid": len(valid),
        "n_error": len(results) - len(valid),
        "gaps_micro_precision": micro_p,
        "gaps_micro_recall": micro_r,
        "gaps_micro_f1": micro_f1,
        "gaps_macro_precision": macro_p,
        "gaps_macro_recall": macro_r,
        "gaps_base_precision": base_p,
        "gaps_base_recall": base_r,
        "gaps_base_k": k,
        "gaps_recall_lift": recall_lift,
        "missed_gaps": sorted(missed),
        "evidence_ratio": ev_ratio,
        "evidence_avg_contain": ev_avg,
        "evidence_hit": ev_hit,
        "evidence_scored": ev_scored,
        "evidence_empty": ev_empty,
        "evidence_short": ev_short,
        "evidence_null_ratio": evidence_null_baseline(rows, chunks),
        "avg_total_tokens": sum(tokens) / len(tokens) if tokens else float("nan"),
        "cache_hit_rate": cache_hit_rate,
        "effective_cost_cny": effective_cost_cny,
        "avg_latency_ms": sum(lat) / len(lat) if lat else float("nan"),
        "p50_latency_ms": _pct([float(x) for x in lat], 50),
        "p95_latency_ms": _pct([float(x) for x in lat], 95),
    }


def append_report(arm: str, fp: str, m: dict, tstamp: str) -> None:
    lines = []
    lines.append("")
    lines.append(f"## {arm} @ {tstamp}")
    lines.append("")
    lines.append(f"- 知识库指纹：`{fp}`")
    lines.append(f"- 样本：{m['n_valid']}/{m['n_total']} 条成功（{m['n_error']} 条失败）")
    lines.append("")
    lines.append("### gaps（逐 JD，不再池化）")
    lines.append(f"- 微平均 precision = {m['gaps_micro_precision']:.3f}，recall = {m['gaps_micro_recall']:.3f}，F1 = {m['gaps_micro_f1']:.3f}")
    lines.append(f"- 宏平均 precision = {m['gaps_macro_precision']:.3f}，recall = {m['gaps_macro_recall']:.3f}")
    lines.append(f"- 等预算平凡基线（恒输出全局 top-{m['gaps_base_k']}）：precision = {m['gaps_base_precision']:.3f}，recall = {m['gaps_base_recall']:.3f} → recall 提升 {m['gaps_recall_lift']:.1f}x")
    if m["missed_gaps"]:
        lines.append(f"- 漏召回（top10）：{'、'.join(m['missed_gaps'][:10])}")
    lines.append("")
    lines.append("### evidence 溯源")
    lines.append(f"- 溯源率（覆盖度≥{EVIDENCE_THRESHOLD}）= {m['evidence_ratio']:.3f}（{m['evidence_hit']}/{m['evidence_scored']}，空 {m['evidence_empty']}，过短 {m['evidence_short']}）｜ null baseline = {m['evidence_null_ratio']:.3f}")
    lines.append(f"- 平均覆盖度 = {m['evidence_avg_contain']:.3f}")
    lines.append("")
    lines.append("### 成本 / 延迟")
    lines.append(f"- 平均 total_tokens = {m['avg_total_tokens']:.0f}，平均延迟 = {m['avg_latency_ms']:.0f}ms，P50 = {m['p50_latency_ms']:.0f}ms，P95 = {m['p95_latency_ms']:.0f}ms")
    lines.append(f"- 缓存命中率 = {m['cache_hit_rate']:.3f}，有效成本 = {m['effective_cost_cny']:.4f} 元（off-peak：miss×1.5 + hit×0.05 + output×4.5，均 /1e6）")
    lines.append("")
    lines.append(f"口径说明：gaps 逐 JD 微/宏平均（弃池化，带等预算平凡基线）；evidence 带 null baseline（JD 原文假 evidence）。match_score 已证伪移除，不再输出。溯源率 = evidence 去空白+去标点切 3-gram，<6 字不计入，与 chunk 展示串及 body 算覆盖度取最大，≥{EVIDENCE_THRESHOLD} 算溯源成功。")
    with open(BASE.parent / "reports" / "report.md", "a", encoding="utf-8") as f:
        f.write("\n".join(lines))


def run(
    arm: str,
    limit: int | None,
    tag: str | None = None,
    search_policy_observe_only: bool = False,
    jd_ids: set[str] | None = None,
) -> None:
    rows = load_dataset()
    if jd_ids is not None:
        rows = [row for row in rows if row["jd_id"] in jd_ids]
    if limit:
        rows = rows[:limit]
    alias_map = load_aliases()
    chunks = load_chunks()
    fp = kb_fingerprint()
    tstamp = time.strftime("%Y-%m-%d %H:%M:%S")

    raw_name = f"raw_{arm}_{tag}.jsonl" if tag else f"raw_{arm}.jsonl"
    raw_path = BASE.parent / "results" / raw_name
    results = []
    with open(raw_path, "w", encoding="utf-8") as f:
        for row in rows:
            rec = eval_one(arm, row, search_policy_observe_only)
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            results.append(rec)
            tag = "ERR" if rec["error"] else "OK "
            print(f"{rec['jd_id']} {tag} tokens={rec['total_tokens']} {rec['error'] or ''}")

    m = compute_metrics(results, rows, alias_map, chunks)
    append_report(arm, fp, m, tstamp)
    print("\n===== 指标 =====")
    for k, v in m.items():
        if k != "missed_gaps":
            print(f"{k}: {v}")


def run_from_raw(arm: str) -> None:
    """从 eval/raw_<arm>.jsonl 重算指标并写 report，不调 LLM（口径改版后复盘旧 arm 用）。"""
    raw_path = BASE.parent / "results" / f"raw_{arm}.jsonl"
    if not raw_path.exists():
        print(f"无 raw 文件：{raw_path}")
        sys.exit(1)
    results = [json.loads(l) for l in raw_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not results:
        print("raw 文件为空")
        sys.exit(1)
    rows = load_dataset()
    alias_map = load_aliases()
    chunks = load_chunks()
    fp = kb_fingerprint()
    tstamp = time.strftime("%Y-%m-%d %H:%M:%S")
    m = compute_metrics(results, rows, alias_map, chunks)
    append_report(arm, fp, m, tstamp)
    print("\n===== 指标（重算自 raw，未调 LLM）=====")
    for k, v in m.items():
        if k != "missed_gaps":
            print(f"{k}: {v}")


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    arm = args[0] if args else None
    if arm not in ("agent-baseline", "workflow", "full-context"):
        print(__doc__)
        sys.exit(1)
    if "--from-raw" in sys.argv:
        run_from_raw(arm)
        return
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    tag = None
    if "--tag" in sys.argv:
        tag = sys.argv[sys.argv.index("--tag") + 1]
    jd_ids = None
    if "--jd-ids" in sys.argv:
        jd_ids = set(sys.argv[sys.argv.index("--jd-ids") + 1].split(","))
    search_policy_observe_only = "--search-policy-observe-only" in sys.argv
    if search_policy_observe_only and arm != "agent-baseline":
        print("--search-policy-observe-only 仅适用于 agent-baseline")
        sys.exit(1)
    run(arm, limit, tag, search_policy_observe_only, jd_ids)


if __name__ == "__main__":
    main()

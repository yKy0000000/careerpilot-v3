import json
from pathlib import Path

from agent.prompts import SYSTEM_PROMPT
from agent.retrieval import MODEL_NAME, _get_client
from agent.save import save_analysis
from agent.schema import MAX_REASONING_LENGTH, validate, validate_tool_arguments
from agent.search_policy import SEARCH_TOOL_NAME, SearchPolicy, SearchState
from agent.tools import TOOLS, TOOL_IMPLS, search_my_experience_with_metadata

client = _get_client()

MAX_ITERATIONS = 8
MAX_VALIDATION_REPAIRS = 1
MAX_TOOL_ARGUMENT_REPAIRS = 1
MAX_TOTAL_RETRIES = 2


def _truncate_reasoning_if_only_error(result: dict) -> dict | None:
    """仅当截断 reasoning 即可通过完整 schema 时，返回本地修复后的副本。"""
    reasoning = result.get("reasoning") if isinstance(result, dict) else None
    if not isinstance(reasoning, str) or len(reasoning) <= MAX_REASONING_LENGTH:
        return None
    repaired = {**result, "reasoning": reasoning[:MAX_REASONING_LENGTH]}
    valid, _ = validate(repaired)
    return repaired if valid else None


def _outcome(
    *,
    status: str,
    jd_id: str,
    result: dict | None,
    iterations: int,
    total_tokens: int,
    hit_tokens: int,
    miss_tokens: int,
    per_turn_cache: list[dict],
    tool_trace: list[dict],
    validation_trace: list[dict],
    retry_counts: dict,
    termination_reason: str | None = None,
    termination_detail: str | None = None,
) -> dict:
    return {
        "status": status,
        "termination_reason": termination_reason,
        "termination_detail": termination_detail,
        "jd_id": jd_id,
        "result": result,
        "iterations": iterations,
        "total_tokens": total_tokens,
        "hit_tokens": hit_tokens,
        "miss_tokens": miss_tokens,
        "per_turn_cache": per_turn_cache,
        "tool_trace": tool_trace,
        "validation_trace": validation_trace,
        "retry_counts": dict(retry_counts),
    }


def run_agent(jd: str, jd_id: str, *, search_policy_observe_only: bool = False) -> dict:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": jd},
    ]
    total_tokens = 0
    hit_tokens = 0
    miss_tokens = 0
    per_turn_cache = []
    tool_trace = []
    validation_trace = []
    retry_counts = {"validation": 0, "tool_argument": 0, "total": 0}
    search_policy = SearchPolicy(observe_only=search_policy_observe_only)
    search_state = SearchState()
    previous_tool_signature = None
    consecutive_duplicate_warnings = 0

    def finish(
        status: str,
        iteration: int,
        reason: str | None = None,
        detail: str | None = None,
        result: dict | None = None,
    ) -> dict:
        return _outcome(
            status=status,
            termination_reason=reason,
            termination_detail=detail,
            jd_id=jd_id,
            result=result,
            iterations=iteration,
            total_tokens=total_tokens,
            hit_tokens=hit_tokens,
            miss_tokens=miss_tokens,
            per_turn_cache=per_turn_cache,
            tool_trace=tool_trace,
            validation_trace=validation_trace,
            retry_counts=retry_counts,
        )

    for iteration in range(1, MAX_ITERATIONS + 1):
        response = client.chat.completions.create(
            model=MODEL_NAME,
            temperature=0,
            messages=messages,
            response_format={"type": "json_object"},
            tools=TOOLS,
            extra_body={"thinking": {"type": "disabled"}},
        )
        msg = response.choices[0].message
        finish_reason = response.choices[0].finish_reason
        usage = response.usage.model_dump()
        total_tokens += response.usage.total_tokens
        hit = usage.get("prompt_cache_hit_tokens", 0)
        miss = usage.get("prompt_cache_miss_tokens", 0)
        hit_tokens += hit
        miss_tokens += miss
        per_turn_cache.append({"turn": iteration, "hit": hit, "miss": miss})

        if finish_reason == "stop":
            validation_attempt = len(validation_trace) + 1
            print(f"[validation] turn={iteration} attempt={validation_attempt} status=started")
            try:
                result = json.loads(msg.content)
                valid, validation_error = validate(result)
            except json.JSONDecodeError as exc:
                result = None
                valid = False
                validation_error = (
                    f"JSON 格式错误：第 {exc.lineno} 行第 {exc.colno} 列，{exc.msg}。"
                    "请输出可解析的完整 JSON object"
                )

            if not valid:
                locally_repaired = (
                    _truncate_reasoning_if_only_error(result)
                    if isinstance(result, dict)
                    else None
                )
                if locally_repaired is not None:
                    result = locally_repaired
                    validation_trace.append({
                        "turn": iteration,
                        "error": validation_error,
                        "action": "local_truncate_reasoning",
                    })
                    print("[validation] action=local_truncate_reasoning status=passed")
                else:
                    validation_trace.append({"turn": iteration, "error": validation_error})
                    print(
                        f"[validation] turn={iteration} attempt={validation_attempt} "
                        f"status=failed error={validation_error}"
                    )
                    if retry_counts["validation"] >= MAX_VALIDATION_REPAIRS:
                        validation_trace[-1]["action"] = "terminate"
                        return finish("failed", iteration, "validation_error", validation_error)
                    if retry_counts["total"] >= MAX_TOTAL_RETRIES:
                        validation_trace[-1]["action"] = "terminate"
                        return finish("terminated", iteration, "limit_exceeded", "总重试预算耗尽")
                    retry_counts["validation"] += 1
                    retry_counts["total"] += 1
                    validation_trace[-1]["action"] = "feedback_to_model"
                    print("[validation] action=feedback_to_model repairs=1/1")
                    messages.append(msg)
                    messages.append({
                        "role": "user",
                        "content": (
                            "你上一轮的最终 JSON 未通过结果 schema 校验。\n"
                            f"具体错误：{validation_error}\n"
                            "请只修复明确指出的结构或字段错误，并重新输出完整 JSON。"
                            "不要调用工具，不要输出 JSON 之外的文字。"
                        ),
                    })
                    continue

            print(
                f"[validation] turn={iteration} attempt={validation_attempt} "
                f"status=passed repairs={retry_counts['validation']}"
            )
            print(f"模型已完成迭代,迭代次数：{iteration}轮")
            print("======== 最终结果 ========")
            outcome = finish("success", iteration, result=result)
            save_analysis(jd_id, result, iteration, total_tokens)
            return outcome

        if finish_reason == "tool_calls":
            print(f"模型第{iteration}轮调用工具")
            messages.append(msg)
            for tool_call in msg.tool_calls:
                tool_name = tool_call.function.name
                raw_arguments = tool_call.function.arguments
                print("调用工具：", tool_name)
                trace_entry = {
                    "turn": iteration,
                    "tool": tool_name,
                    "raw_arguments": raw_arguments,
                }

                try:
                    arguments = json.loads(raw_arguments)
                except json.JSONDecodeError as exc:
                    arguments = None
                    argument_error = (
                        f"{tool_name} 参数 JSON 错误：第 {exc.lineno} 行"
                        f"第 {exc.colno} 列，{exc.msg}"
                    )
                else:
                    _, argument_error = validate_tool_arguments(tool_name, arguments, TOOLS)

                if argument_error:
                    trace_entry.update({"args": arguments, "argument_error": argument_error})
                    tool_trace.append(trace_entry)
                    print(f"工具参数校验失败：{argument_error}")
                    if retry_counts["tool_argument"] >= MAX_TOOL_ARGUMENT_REPAIRS:
                        trace_entry["action"] = "terminate"
                        return finish("failed", iteration, "tool_argument_error", argument_error)
                    if retry_counts["total"] >= MAX_TOTAL_RETRIES:
                        trace_entry["action"] = "terminate"
                        return finish("terminated", iteration, "limit_exceeded", "总重试预算耗尽")
                    retry_counts["tool_argument"] += 1
                    retry_counts["total"] += 1
                    trace_entry["action"] = "feedback_to_model"
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": (
                            f"ToolArgumentError: {argument_error}。"
                            "请修正参数后重试一次，或跳过该工具继续分析。"
                        ),
                    })
                    continue

                trace_entry["args"] = arguments
                print("参数内容", arguments)
                signature = f"{tool_name}:{json.dumps(arguments, ensure_ascii=False, sort_keys=True)}"
                if signature == previous_tool_signature:
                    consecutive_duplicate_warnings += 1
                    trace_entry["duplicate"] = True
                    if consecutive_duplicate_warnings >= 2:
                        trace_entry["action"] = "terminate"
                        tool_trace.append(trace_entry)
                        return finish(
                            "terminated",
                            iteration,
                            "duplicate_tool_call",
                            "连续三次出现相同工具名和参数",
                        )
                    if retry_counts["total"] >= MAX_TOTAL_RETRIES:
                        trace_entry["action"] = "terminate"
                        tool_trace.append(trace_entry)
                        return finish(
                            "terminated",
                            iteration,
                            "limit_exceeded",
                            "总重试预算耗尽",
                        )
                    retry_counts["total"] += 1
                    trace_entry["action"] = "feedback_to_model"
                    tool_result = "DuplicateToolCall: 该调用已执行。请使用已有结果，或改用不同参数。"
                    trace_entry["result_preview"] = tool_result
                    tool_trace.append(trace_entry)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_result,
                    })
                    continue

                previous_tool_signature = signature
                consecutive_duplicate_warnings = 0
                trace_entry["duplicate"] = False

                try:
                    if tool_name == SEARCH_TOOL_NAME:
                        decision = search_policy.before_search(arguments["query"], search_state)
                        trace_entry.update({
                            "policy_mode": "observe_only" if search_policy.observe_only else "enforce",
                            "search_count": search_state.search_count,
                            "query": arguments["query"],
                            "returned_chunks": 0,
                            "new_chunks": 0,
                            "novelty_ratio": None,
                            "low_novelty_streak": search_state.low_novelty_streak,
                        })
                        if not decision.allowed:
                            tool_result = (
                                f"SearchPolicyRejected: {decision.reason}。"
                                "请停止重复检索，基于已有证据继续分析。"
                            )
                            trace_entry.update({
                                "policy_rejected": True,
                                "policy_reason": decision.reason,
                            })
                        else:
                            search_result = search_my_experience_with_metadata(**arguments)
                            tool_result = search_result.content
                            trace_entry.update(search_policy.after_search(
                                arguments["query"], search_result.chunk_ids, search_state
                            ))
                            trace_entry.update({
                                "policy_rejected": False,
                                "policy_would_reject": decision.shadow_rejection_reason is not None,
                                "policy_shadow_reason": decision.shadow_rejection_reason,
                            })
                    else:
                        tool_result = TOOL_IMPLS[tool_name](**arguments)
                except Exception as exc:
                    detail = f"{type(exc).__name__}: {exc}"
                    trace_entry.update({"execution_error": detail, "action": "terminate"})
                    tool_trace.append(trace_entry)
                    return finish("failed", iteration, "tool_execution_error", detail)

                trace_entry["result_preview"] = tool_result[:200]
                tool_trace.append(trace_entry)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result,
                })
            continue

        if finish_reason == "length":
            print("模型此轮输出达到文本上限,建议修改max_token")
            return finish("terminated", iteration, "limit_exceeded", "模型输出达到长度上限")

        return finish(
            "failed",
            iteration,
            "tool_execution_error",
            f"未知 finish_reason: {finish_reason}",
        )

    return finish(
        "terminated",
        MAX_ITERATIONS,
        "limit_exceeded",
        f"达到 {MAX_ITERATIONS} 轮上限",
    )


if __name__ == "__main__":
    jd_path = Path(__file__).resolve().parent.parent / "eval" / "jds" / "jd-05.md"
    jd = jd_path.read_text(encoding="utf-8")
    jd_id = jd_path.stem
    print(run_agent(jd, jd_id))

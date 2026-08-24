import json
from pathlib import Path

from agent.prompts import SYSTEM_PROMPT
from agent.retrieval import _get_client, MODEL_NAME
from agent.schema import validate
from agent.tools import TOOLS, TOOL_IMPLS
from agent.save import save_analysis

client = _get_client()


def run_agent(jd: str,jd_id: str) -> dict:
    messages = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": jd}]
    total_tokens = 0
    hit_tokens = 0
    miss_tokens = 0
    per_turn_cache = []
    tool_trace = []
    for i in range(1,9):
        response=client.chat.completions.create(
            model=MODEL_NAME,
            temperature=0,
            messages=messages,
            response_format={"type": "json_object"},
            tools=TOOLS,
            extra_body={"thinking": {"type": "disabled"}}
        )
        msg=response.choices[0].message
        cur_situation=response.choices[0].finish_reason
        d = response.usage.model_dump()
        total_tokens += response.usage.total_tokens
        hit = d.get("prompt_cache_hit_tokens", 0)
        miss = d.get("prompt_cache_miss_tokens", 0)
        hit_tokens += hit
        miss_tokens += miss
        per_turn_cache.append({"turn": i, "hit": hit, "miss": miss})

        if cur_situation == "stop":
            result = json.loads(msg.content)
            valid, val_err = validate(result)
            if not valid:
                raise ValueError(f"validate 失败: {val_err}")
            print(f"模型已完成迭代,迭代次数：{i}轮")
            print("======== 最终结果 ========")
            outcome= {
                "jd_id": jd_id,
                "result": result,
                "iterations": i,
                "total_tokens": total_tokens,
                "hit_tokens": hit_tokens,
                "miss_tokens": miss_tokens,
                "per_turn_cache": per_turn_cache,
                "tool_trace": tool_trace,
            }
            save_analysis(jd_id,result,i,total_tokens)
            return outcome
        elif cur_situation == "tool_calls":
            print(f"模型第{i}轮调用工具")
            messages.append(msg)
            for tc in msg.tool_calls:
                print("调用工具：", tc.function.name)
                args = json.loads(tc.function.arguments)
                print("参数内容", args)
                try:
                    tool_result = TOOL_IMPLS[tc.function.name](**args)
                except Exception as e:
                    tool_result = f"{type(e).__name__}: {str(e)}。建议：换一个更具体的 query 重试，或跳过该项继续分析。"
                tool_trace.append({
                    "turn": i,
                    "tool": tc.function.name,
                    "args": args,
                    "result_preview": tool_result[:200],
                })
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": tool_result})
        elif cur_situation == "length":
            print("模型此轮输出达到文本上限,建议修改max_token")
            raise RuntimeError("输出被截断")
    else :
        raise RuntimeError("达到迭代次数上限,当前内容")

if __name__ == "__main__":
    jd_path = Path(__file__).resolve().parent.parent / "eval" / "jds" / "jd-05.md"
    jd = jd_path.read_text(encoding="utf-8")
    jd_id = jd_path.stem
    print(run_agent(jd,jd_id))
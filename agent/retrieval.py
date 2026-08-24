import os
import json
from pathlib import Path

from openai import OpenAI
from dotenv import load_dotenv

from kb.index import load_index, search
from agent.schema import validate
from agent.prompts import SYSTEM_PROMPT

load_dotenv()

INDEX_PATH = Path(__file__).resolve().parent.parent / "kb" / "index.npz"

MODEL_NAME = "deepseek-v4-flash"

_client = None


def _get_client():
    """懒加载 LLM client，复用 L2 学到的套路"""
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
        )
    return _client


def _reconstruct_chunks(headings, bodies, sources):
    """把 npz 读回的四个数组重组成 list[dict]"""
    return [
        {"heading": str(h), "body": str(b), "source": str(s)}
        for h, b, s in zip(headings, bodies, sources)
    ]


def run_workflow(jd: str, top_k: int = 5) -> tuple:
    """固定前置检索：JD → 检索 top-k → 拼 prompt → 调 LLM → validate → 返回 (result, usage)"""

    # 1. 加载索引 + 重组 chunks
    headings, bodies, sources, embeddings = load_index(INDEX_PATH)
    chunks = _reconstruct_chunks(headings, bodies, sources)

    # 2. 检索
    top_chunks = search(jd, embeddings, chunks, top_k)

    # L3 观察用：打印检索到的 top-k（人工判断命中情况就靠这个）
    print("=" * 40)
    for i, c in enumerate(top_chunks, 1):
        print(f"[top{i} | 来源 {c['source']}] {c['heading']}")
        print(f"  {c['body'][:80]}")
    print("=" * 40)

    # 3. 拼 prompt（system + chunk 原文 + JD）
    retrieved_text = "\n\n".join(
        f"[来源 {c['source']}] {c['heading']}\n{c['body']}" for c in top_chunks
    )
    user_content = f"候选人相关资料：\n\n{retrieved_text}\n\n=====\n岗位 JD：\n{jd}"

    # 4. 调 LLM
    client = _get_client()
    response = client.chat.completions.create(
        model=MODEL_NAME,
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        response_format={"type": "json_object"},
        extra_body={"thinking": {"type": "disabled"}}
    )
    result = json.loads(response.choices[0].message.content)

    # 5. validate
    valid, msg = validate(result)
    if not valid:
        raise ValueError(f"validate 失败: {msg}")

    return result,response.usage


def run_full_context(jd: str) -> tuple:
    """full-context arm：不检索，KB 全灌进 prompt，单次 LLM 调用。返回 (result, usage)。"""
    headings, bodies, sources, _ = load_index(INDEX_PATH)
    chunks = _reconstruct_chunks(headings, bodies, sources)
    retrieved_text = "\n\n".join(
        f"[来源 {c['source']}] {c['heading']}\n{c['body']}" for c in chunks
    )
    user_content = f"候选人相关资料（完整知识库）：\n\n{retrieved_text}\n\n=====\n岗位 JD：\n{jd}"

    client = _get_client()
    response = client.chat.completions.create(
        model=MODEL_NAME,
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        response_format={"type": "json_object"},
        extra_body={"thinking": {"type": "disabled"}}
    )
    result = json.loads(response.choices[0].message.content)

    valid, msg = validate(result)
    if not valid:
        raise ValueError(f"validate 失败: {msg}")

    return result, response.usage


if __name__ == "__main__":
    jd_path = Path(__file__).resolve().parent.parent / "eval" / "jds" / "jd-05.md"
    jd = jd_path.read_text(encoding="utf-8")
    result = run_workflow(jd)
    print(json.dumps(result, ensure_ascii=False, indent=2))

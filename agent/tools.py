from kb.index import load_index, search
from agent.retrieval import _reconstruct_chunks, INDEX_PATH
import httpx
import trafilatura
from data.company import company

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_my_experience",
            "description": "输入一个query，返回知识库中相关的候选人经历片段",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "不要整段JD都放入，每个query中只能有一个技术要求，光秃秃的名词（如只写 'API'）不行，要带动作（如 '构建异步 API 接口'）"},
                    "top_k": {"type": "integer", "description": "默认 3，最多 8"},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_jd",
            "description": "当 JD 只给了链接、没有正文时，抓取该链接的正文，当 JD 正文已完整提供时不要调用",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string","description": "不要放入整段JD，需要一个完整的、可以打开的链接，以http或者https开头，没有完整 url 时不要调、不要编造"},
                },
                "required": ["url"],
                "additionalProperties": False,
            }
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_company",
            "description": "输入公司名，返回公司具体业务简介，当JD中只有负责系统的设计与开发这种通用描述时调用,JD写'负责RAG知识库从0搭建、向量检索优化'这种已明确技术栈的，不调。",
            "parameters": {
                "type": "object",
                "properties": {
                    "company_key": {"type": "string","description": "公司级粒度名称，如'腾讯'，去掉事业群/部门/职级后缀（'腾讯IEG'→'腾讯'）"}
                },
                "required": ["company_key"],
                "additionalProperties": False,
            }
        },
    }
]

def search_my_experience(query: str, top_k: int = 3):

    # 1. 加载索引 + 重组 chunks
    headings, bodies, sources, embeddings = load_index(INDEX_PATH)
    chunks = _reconstruct_chunks(headings, bodies, sources)

    # 2. 检索
    top_chunks = search(query, embeddings, chunks, top_k)

    # 5. 拼 prompt（system + chunk 原文 + JD）
    retrieved_text = "\n\n".join(
        f"[来源 {c['source']}] {c['heading']}\n{c['body']}" for c in top_chunks
    )
    return retrieved_text

def fetch_jd(url: str) -> str:
    try:
        resp = httpx.get(url, timeout=10, follow_redirects=True)
        resp.raise_for_status()          # 非 2xx 抛异常
        text = trafilatura.extract(resp.text)
        if not text:
            return "错误：抓取到的页面无法提取出正文"
        return text
    except Exception as e:
        return f"{type(e).__name__}: {str(e)}。建议：跳过该JD"

def search_company(company_key: str):
    for key in company.keys():
        if company_key == key:
            return company[key]
    return "本地关键词表未找到，请基于 JD 已有内容继续分析"


TOOL_IMPLS = {"search_my_experience": search_my_experience,
              "fetch_jd": fetch_jd,
              "search_company": search_company
              }
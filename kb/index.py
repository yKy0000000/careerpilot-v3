from pathlib import Path
import re
from sentence_transformers import SentenceTransformer

import numpy as np

_model = None                        # 模块级变量：存"加载好的模型"
QUERY_PREFIX = "为这个句子生成表示以用于检索相关文章："

def load_docs(docs_dir: Path) -> list[dict]:
    """扫描 docs/ 下所有 .md，返回 [{path, text}]"""
    results = []
    for p in docs_dir.glob("*.md"):
        results.append({"path": p, "text": p.read_text(encoding="utf-8")})
    return results

def split_chunks(text: str) -> list[dict]:
    results = []
    pieces = re.split(r"^##\s*", text, flags=re.MULTILINE)   # 加 \s* 吃掉标题后的空格

    title = ""          # 先声明，避免没有 # 时变量不存在
    tech = ""
    for line in pieces[0].split("\n"):          # 遍历"行"
        if line.startswith("# "):
            title = line[2:].strip()            # 赋值，不是 append
        elif line.startswith("> "):
            tech = line[2:].strip()

    for line in pieces[1:]:                     # 每个已是完整 chunk
        temp = line.split("\n", 1)
        heading = f"{title} | {tech} | {temp[0].strip()}"   # 变量拼进去
        results.append({"heading": heading, "body": temp[1].strip()})

    return results

def _get_model():
    """加载一次，之后复用"""
    global _model
    if _model is None:               # 第一次调用才加载，之后跳过
        _model = SentenceTransformer(r"C:\Users\26742\.cache\modelscope\models\AI-ModelScope--bge-small-zh-v1.5\snapshots\master")
    return _model

def embed_texts(texts: list[str]) -> np.ndarray:
    """批量向量化，返回 (n, dim) 数组"""
    model = _get_model()  # 拿模型（第一次慢，之后快）
    return model.encode(texts, normalize_embeddings=True)

def save_index(chunks, embeddings, path):
    np.savez(
        path,
        headings=np.array([c["heading"] for c in chunks]),   # (n,) 字符串数组
        bodies=np.array([c["body"] for c in chunks]),
        sources=np.array([c["source"] for c in chunks]),
        embeddings=embeddings,                                # (n, dim)
    )

def load_index(path):
    data = np.load(path)
    return data["headings"], data["bodies"], data["sources"], data["embeddings"]

def search(query: str, embeddings: np.ndarray, chunks, top_k: int = 5):
    # 1. 编码 query（注意：bge 的 query 侧要加指令前缀）
    model = _get_model()
    q = model.encode([QUERY_PREFIX + query], normalize_embeddings=True)   # (1, dim)

    # 2. 算相似度：矩阵乘法一次算完所有 chunk 的分数
    scores = (embeddings @ q.T).flatten()                            # (n,)

    # 3. 排序取 top-k：argsort 升序，[::-1] 降序，取前 k 个下标
    top_idx = np.argsort(scores)[::-1][:top_k]

    # 4. 按下标取回 chunk
    return [chunks[i] for i in top_idx]    # ⬜ 返回 raw 还是 text


def build(docs_dir: Path, index_path: Path) -> int:
    """离线构建：读文档 → 切块 → 附加 source → 向量化 → 存盘，返回 chunk 数"""
    chunks = []
    for doc in load_docs(docs_dir):
        for c in split_chunks(doc["text"]):
            c["source"] = doc["path"].name   # source 在这里附加，不在 split_chunks 里
            chunks.append(c)
    texts = [f"{c['heading']}\n{c['body']}" for c in chunks]   # 向量化时拼 heading+body
    embeddings = embed_texts(texts)
    save_index(chunks, embeddings, index_path)
    return len(chunks)


if __name__ == "__main__":
    docs = Path(__file__).parent / "docs"
    idx = Path(__file__).parent / "index.npz"
    n = build(docs, idx)
    print(f"索引重建完成：{n} 个 chunk")

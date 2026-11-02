"""
Dify 外部知识库 API 服务 - 输配电专业知识库
运行方式：python dify_external_kb.py
访问地址：http://0.0.0.0:8000
"""

from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
import requests
import re
from typing import List

app = FastAPI(title="输配电专业知识库 - Dify外部知识库API")

# ==========================================================
# 配置项 - 上传GitHub后请修改为你的仓库地址
# ==========================================================
# GitHub raw 文件地址模板
# 格式：https://raw.githubusercontent.com/你的用户名/你的仓库名/main/docs/
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/你的用户名/distribution-grid-kb/main/docs/"

# 知识库文件列表
GITHUB_FILES = [
    "01-配电故障处理.md",
    "02-输配电计算方法.md",
    "03-专业术语表.md",
    "04-配电网技术导则摘要.md",
]

# API Key - Dify里要填一样的
API_KEY = "distribution-kb-2026"
# ==========================================================

# 启动时预加载所有文档
documents = {}

def load_docs():
    """从GitHub加载所有文档"""
    print("=" * 50)
    print("开始加载知识库文档...")
    for fname in GITHUB_FILES:
        url = GITHUB_RAW_BASE + fname
        try:
            resp = requests.get(url, timeout=15)
            if resp.status_code == 200:
                documents[fname] = resp.text
                print(f"  ✅ 加载成功: {fname} ({len(resp.text)} 字)")
            else:
                print(f"  ❌ 加载失败: {fname} HTTP {resp.status_code}")
        except Exception as e:
            print(f"  ❌ 加载出错: {fname} - {e}")
    print(f"共加载 {len(documents)} 个文档")
    print("=" * 50)

load_docs()


class RetrievalSetting(BaseModel):
    top_k: int
    score_threshold: float


class RetrievalRequest(BaseModel):
    knowledge_id: str
    query: str
    retrieval_setting: RetrievalSetting


def simple_search(query: str, doc_content: str) -> float:
    """
    简单关键词匹配算法
    统计query里每个词在文档片段中出现的次数，计算相似度分数
    """
    # 中文简易分词：提取2-6字的中文词组
    query_words = re.findall(r'[\u4e00-\u9fa5]{2,6}', query)
    if not query_words:
        return 0.0

    score = 0.0
    for word in query_words:
        count = doc_content.count(word)
        # 每个词最多贡献1分，出现5次以上算满分
        score += min(count / 5.0, 1.0)

    # 归一化到 0-1
    return min(score / len(query_words), 1.0)


def split_chunks(text: str, chunk_size: int = 300, overlap: int = 80) -> List[str]:
    """把长文档切成小片段，模拟Dify的分段效果"""
    chunks = []
    step = chunk_size - overlap
    for i in range(0, len(text), step):
        chunk = text[i:i + chunk_size]
        if chunk.strip():
            chunks.append(chunk.strip())
    return chunks


@app.post("/retrieval")
async def retrieval(req: RetrievalRequest, request: Request):
    """
    Dify外部知识库检索接口
    Dify会POST请求到 /retrieval
    """
    # 验证API Key
    auth_header = request.headers.get("Authorization", "")
    expected_auth = f"Bearer {API_KEY}"
    if auth_header != expected_auth:
        raise HTTPException(
            status_code=401,
            detail={"error_code": 1002, "error_msg": "API Key 验证失败"}
        )

    query = req.query
    top_k = req.retrieval_setting.top_k
    threshold = req.retrieval_setting.score_threshold

    print(f"\n📝 收到查询: {query}")
    print(f"   参数: top_k={top_k}, threshold={threshold}")

    # 遍历所有文档，给每个片段打分
    results = []
    for fname, content in documents.items():
        chunks = split_chunks(content)
        for idx, chunk in enumerate(chunks):
            score = simple_search(query, chunk)
            if score >= threshold:
                results.append({
                    "content": chunk,
                    "score": round(score, 3),
                    "title": fname,
                    "metadata": {
                        "source": f"GitHub知识库: {fname}",
                        "chunk_index": idx,
                        "category": get_category(fname)
                    }
                })

    # 按分数排序，取前 top_k
    results.sort(key=lambda x: x["score"], reverse=True)
    results = results[:top_k]

    print(f"   命中 {len(results)} 个片段")
    for i, r in enumerate(results[:3]):
        print(f"   [{i+1}] 分数={r['score']} 来源={r['title']}")

    return {"records": results}


def get_category(fname: str) -> str:
    """根据文件名判断知识类别"""
    if "故障" in fname:
        return "故障分析"
    elif "计算" in fname:
        return "计算方法"
    elif "术语" in fname:
        return "术语查询"
    elif "导则" in fname:
        return "技术规范"
    return "通用"


@app.get("/health")
async def health():
    """健康检查接口"""
    return {
        "status": "ok",
        "loaded_docs": len(documents),
        "docs": list(documents.keys())
    }


if __name__ == "__main__":
    import uvicorn
    print("\n🚀 启动输配电知识库API服务...")
    print(f"   地址: http://0.0.0.0:8000")
    print(f"   健康检查: http://localhost:8000/health")
    uvicorn.run(app, host="0.0.0.0", port=8000)

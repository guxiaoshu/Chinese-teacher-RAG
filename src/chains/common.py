from __future__ import annotations

from dataclasses import dataclass, field

from ..config import CONFIG
from ..retrieval.retriever import RetrievedDoc

@dataclass
class ChainResult:
    content: str #最终给用户看的回答文本
    citations: list[dict] = field(default_factory=list)
    #引用来源列表，对应每一条检索到的文档，用来做文末引用标注、溯源
    data: dict | None = None
    #可选附加载荷，放调试信息、检索分数、意图、
    #扩展 query 等，给后台日志 / 调试面板用，不给学生老师展示

def build_context(docs: list[RetrievedDoc]) -> tuple[str, list[dict]]:
    #把检索回来的 `RetrievedDoc` 列表，
    #拼装成**给 LLM 读的上下文字符串** + 结构化引用 citations 数组
    if not docs:
        return "（未检索到相关内容，请先上传资料入库）", []
    parts: list[str] = []
    citations: list[dict] = []
    for i, d in enumerate(docs, 1):
        article = (d.meta.get("article") or "").strip()
        label = f"[{i}] 来源：{d.source_label()}｜类型：{d.doc_type}"
        if article:
            label += f"｜篇目：{article}"
        parts.append(f"{label}\n{d.text}")
        citations.append({
            "index": i,
            "source_file": d.source_file,
            "library": d.library,
            "doc_type": d.doc_type,
            "score": round(float(d.score), 3),
            "authority": d.meta.get("authority", ""),
            "grade": d.meta.get("grade", ""),
            "article": d.meta.get("article", ""),
            "generated": d.meta.get("generated"),
        })
    return "\n\n---\n\n".join(parts), citations


def with_memory(user: str, memory: str) -> str:
    #**业务侧的用户长期记忆注入**，不是向量记忆，是前置文本硬注入：
    """把老师希望长期记住的上下文置顶注入到用户消息里（空则原样返回）。"""
    m = (memory or "").strip()
    if not m:
        return user
    return f"【老师希望你长期记住的上下文，生成时须优先遵循】\n{m}\n\n{user}"


REFUSAL_MESSAGE = "抱歉，知识库里没有检索到与这个问题相关的内容，无法作答。建议先上传相关教学资料，或换一种更具体的问法。"


def should_refuse(docs: list[RetrievedDoc]) -> bool:
    #RAG 经典的拒答 / 幻觉防护开关：
# 1. 一条文档都没召回 → 拒答
# 2. 配置里 `retrieval.refuse_score > 0` 时：取这批文档里**最高分**，最高分都低于阈值 → 拒答
# 3. 阈值设为 0：关闭分数拒答，哪怕分很低也继续送入 LLM 生成（更容易幻觉）
# 调用顺序：检索、rerank 完成后，先跑 `should_refuse(docs)`
# - 返回 True：直接返回 REFUSAL_MESSAGE，**不再调用生成 LLM**，省 token、防乱编
# - 返回 False：正常走 build_context，把上下文塞给 LLM 生成答案
    """检索不足时判拒答：docs 为空，或最高分低于 config 的 refuse_score 阈值。"""
    if not docs:
        return True
    threshold = float(CONFIG.get("retrieval", {}).get("refuse_score", 0) or 0)
    if threshold > 0:
        return max(d.score for d in docs) < threshold
    return False

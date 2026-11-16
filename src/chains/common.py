from __future__ import annotations

from dataclasses import dataclass, field

from ..config import CONFIG
from ..retrieval.retriever import RetrievedDoc

@dataclass
class ChainResult:
    content: str
    citations: list[dict] = field(default_factory=list)
    data: dict | None = None

def build_context(docs: list[RetrievedDoc]) -> tuple[str, list[dict]]:
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
        })
    return "\n\n---\n\n".join(parts), citations


def with_memory(user: str, memory: str) -> str:
    """把老师希望长期记住的上下文置顶注入到用户消息里（空则原样返回）。"""
    m = (memory or "").strip()
    if not m:
        return user
    return f"【老师希望你长期记住的上下文，生成时须优先遵循】\n{m}\n\n{user}"


REFUSAL_MESSAGE = "抱歉，知识库里没有检索到与这个问题相关的内容，无法作答。建议先上传相关教学资料，或换一种更具体的问法。"


def should_refuse(docs: list[RetrievedDoc]) -> bool:
    """检索不足时判拒答：docs 为空，或最高分低于 config 的 refuse_score 阈值。"""
    if not docs:
        return True
    threshold = float(CONFIG.get("retrieval", {}).get("refuse_score", 0) or 0)
    if threshold > 0:
        return max(d.score for d in docs) < threshold
    return False

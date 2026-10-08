from __future__ import annotations

from ..retrieval.retriever import retrieve
from ..llm.deepseek import get_chat_llm
from ..ingestion.generated import save_generated
from .common import ChainResult, build_context, with_memory

_SYSTEM = """你是老师私人的语文教学答疑助手。为学生答疑时以启发式为主，不直接输出完整答案。

硬性规则：
1. 优先使用老师课堂里用过的例子、批注、学生当时的疑问来引导（来自【私有知识库】）。
2. 启发式：给思路、提示、追问，引导学生自己得出结论；不直接给出标准答案。
3. 引用材料用 [n] 标注，并说明来自【私有知识库】还是【公共基准库】。
4. 语气像老师本人，沿用其教学话术。
"""

def run(query: str, save: bool = True, memory: str = "") -> ChainResult:
    docs = retrieve(query)
    ctx, citations = build_context(docs)
    user = with_memory(f"学生/老师的问题：{query}\n\n可参考的老师过往资料：\n{ctx}", memory)
    llm = get_chat_llm()
    resp = llm.invoke([
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": user},
    ])
    content = resp.content
    if save:
        save_generated("答疑", query, content)
    return ChainResult(content=content, citations=citations)

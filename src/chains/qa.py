from __future__ import annotations

from ..retrieval.retriever import retrieve
from ..retrieval.query_rewrite import rewrite_with_history
from ..llm.deepseek import get_chat_llm
from ..ingestion.generated import save_generated
from .common import ChainResult, build_context, with_memory, should_refuse

_SYSTEM = """你是老师私人的语文教学答疑助手。为学生答疑时以启发式为主，不直接输出完整答案。

硬性规则：
1. 优先使用老师课堂里用过的例子、批注、学生当时的疑问来引导（来自【私有知识库】）。
2. 启发式：给思路、提示、追问，引导学生自己得出结论；不直接给出标准答案。
3. 引用材料用 [n] 标注，并说明来自【私有知识库】还是【公共基准库】。
4. 语气像老师本人，沿用其教学话术。
"""

def run(query: str, save: bool = True, memory: str = "", history: list[dict] | None = None) -> ChainResult:
    history = (history or [])[-12:]  # 最多带最近 6 轮，避免上下文无限增长
    # 多轮：结合历史把提问改写成独立完整的问题（补全「那」「它」等指代）再检索
    search_query = rewrite_with_history(query, history) if history else query
    docs = retrieve(search_query)
    if should_refuse(docs):
        return ChainResult(content="没有检索到老师过往的相关资料，无法进行启发式答疑。建议先上传相关课堂笔记/教案，或换一种更具体的问法。", citations=[])
    ctx, citations = build_context(docs)
    user = with_memory(f"学生/老师的问题：{query}\n\n可参考的老师过往资料：\n{ctx}", memory)
    messages = [{"role": "system", "content": _SYSTEM}, *history, {"role": "user", "content": user}]
    llm = get_chat_llm()
    resp = llm.invoke(messages)
    content = resp.content
    if save:
        save_generated("答疑", query, content)
    return ChainResult(content=content, citations=citations)

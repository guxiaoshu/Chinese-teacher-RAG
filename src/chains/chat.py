"""临时闲聊：不检索、不沉淀，直接多轮对话（像网页版 DeepSeek）。

与「答疑」的区别：
- 答疑：召回私有/公共知识库 + 套启发式教师人设 + 结果自动回库；
- 本模块：纯对话，历史消息原样回传，刷新页面即清空，不写入任何知识库。
"""
from __future__ import annotations

from ..llm.deepseek import get_chat_llm, get_reason_llm

_SYSTEM = "你是一个乐于助人的 AI 助手，用中文回答，直接、准确、简洁。"


def _messages(history: list[dict]) -> list[dict]:
    return [{"role": "system", "content": _SYSTEM}, *history]


def run(history: list[dict], use_reason: bool = False) -> str:
    """同步返回完整回答。history 形如 [{"role":"user"/"assistant","content":"..."}, ...]。"""
    llm = get_reason_llm() if use_reason else get_chat_llm()
    resp = llm.invoke(_messages(history))
    return resp.content


def stream(history: list[dict], use_reason: bool = False):
    """流式返回回答片段（供 st.write_stream 逐字渲染）。"""
    llm = get_reason_llm(streaming=True) if use_reason else get_chat_llm(streaming=True)
    for chunk in llm.stream(_messages(history)):
        if chunk.content:
            yield chunk.content

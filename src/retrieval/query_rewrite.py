from __future__ import annotations

from functools import lru_cache

from ..config import api_key_ready
from ..llm.deepseek import get_chat_llm

_SYSTEM = """你是中学语文检索查询改写器。把老师或学生的口语化提问，改写成更适合向量检索的规范查询短语。

改写规则：
1. 补全篇目/课文名：若提问引用了某篇课文原句或提到某篇目（如"乃不知有汉"出自《桃花源记》），补上《篇目名》。
2. 补全知识点维度：把"乃是什么意思"改写为"文言虚词'乃'的含义和用法"；把"怎么赏析"改写为"现代文赏析/写作手法"。
3. 口语化、指代不明 → 改成书面、具体、完整。例如"那个虚词怎么用"→ 补全所指的虚词与篇目。
4. 只补关键检索信息，不要展开成完整问题，不要无中生有（不确定篇目不要硬加）。
5. 输出一句改写后的检索短语（中文），不要引号、不要解释、不要多余文字。"""

@lru_cache(maxsize=1024)
def _rewrite_cached(q: str) -> str:
    try:
        llm = get_chat_llm(temperature=0.0)
        resp = llm.invoke([
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": q},
        ])
        out = (resp.content or "").strip()
        if 2 <= len(out) <= max(len(q) * 4, 60):
            return out
        return q
    except Exception:
        return q


def rewrite_query(query: str) -> str:
    q = (query or "").strip()
    if not q or not api_key_ready():
        return query
    return _rewrite_cached(q)

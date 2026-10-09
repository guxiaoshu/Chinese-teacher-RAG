from __future__ import annotations

from functools import lru_cache

from ..config import api_key_ready, allowed_grades, allowed_knowledge_points, CONFIG
from ..llm.deepseek import get_chat_llm, invoke_json

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


_EXPAND_SYSTEM = """你是中学语文检索查询扩展器。把老师/学生的提问，扩展成 3 条不同角度的检索短语，用于提升向量 + 关键词的召回率。

规则：
1. 每条都是精炼的检索短语（不是完整句子、不要问号），中文，4~20 字。
2. 第 1 条：补全篇目 + 知识点（如"岳阳楼记 文言虚词 乃 用法"）。
3. 第 2 条：换一个角度，偏教学场景（如"岳阳楼记 重难点 课堂提问 学生易错"）。
4. 第 3 条：偏知识本体（如"岳阳楼记 写作背景 主旨 艺术特色"）。
5. 不确定的篇目/知识点不要硬编，宁少勿错。
6. 只输出 JSON：{"queries": ["...", "...", "..."]}，不要其它文字。"""


@lru_cache(maxsize=1024)
def _expand_cached(q: str) -> list[str]:
    try:
        raw = invoke_json([
            {"role": "system", "content": _EXPAND_SYSTEM},
            {"role": "user", "content": q},
        ], temperature=0.0)
        out = [str(x).strip() for x in (raw.get("queries") or []) if str(x).strip()]
        if not out:
            return [q]
        # 原查询永远放最前，避免扩展把原意带偏；最多保留 multiquery 条
        limit = max(2, int(CONFIG["retrieval"].get("multiquery", 3)))
        return [q] + out[: limit - 1]
    except Exception:
        return [q]


def expand_queries(query: str) -> list[str]:
    q = (query or "").strip()
    if not q or not api_key_ready():
        return [query]
    return _expand_cached(q)


_INTENT_SYSTEM = f"""你是中学语文检索意图解析器。从提问里抽取检索过滤/加权条件。
学段只能是以下之一：{"、".join(allowed_grades())}（无法判断则空串""）
知识点从以下选（可多选，可补相近词）：{"、".join(allowed_knowledge_points())}
只输出 JSON：{{"article": "篇目名（如 岳阳楼记，无则空串）", "grade": "学段", "knowledge_points": ["知识点"], "doc_type": "文档类型（无则空串）"}}，不要其它文字。"""


def _as_list(v) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        return [v] if v else []
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    return [str(v)]


@lru_cache(maxsize=1024)
def _intent_cached(q: str) -> dict:
    try:
        raw = invoke_json([
            {"role": "system", "content": _INTENT_SYSTEM},
            {"role": "user", "content": q},
        ], temperature=0.0)
        return {
            "article": str(raw.get("article") or "").strip(),
            "grade": str(raw.get("grade") or "").strip(),
            "knowledge_points": _as_list(raw.get("knowledge_points")),
            "doc_type": str(raw.get("doc_type") or "").strip(),
        }
    except Exception:
        return {}


def extract_intent(query: str) -> dict:
    q = (query or "").strip()
    if not q or not api_key_ready():
        return {}
    return _intent_cached(q)

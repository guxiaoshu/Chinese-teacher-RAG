from __future__ import annotations

from ..retrieval.retriever import retrieve
from ..llm.deepseek import invoke_json
from ..ingestion.generated import save_generated
from .common import ChainResult, build_context, with_memory

_SYSTEM = """你是学情分析助手，基于老师【私有知识库】里的错题、作答样本、课堂记录，
输出某篇目/单元的学情诊断，帮助老师沉淀教学资产。

硬性规则：
1. 所有结论必须来自检索到的私有文档，不得臆造。
2. 输出 JSON（只输出 JSON）：
{
  "high_freq_errors": ["高频错误1", "..."],
  "confusions": ["易混淆点1", "..."],
  "class_common_issues": ["班级共性错误1", "..."],
  "suggestions": ["针对性教学建议1", "..."]
}
"""

def run(query: str, save: bool = True, memory: str = "") -> ChainResult:
    docs = retrieve(query, library="private")
    ctx, citations = build_context(docs)
    user = with_memory(f"学情分析需求：{query}\n\n检索到的学生错题/作答样本：\n{ctx}", memory)
    data = invoke_json([
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": user},
    ])
    content = _render(data)
    if save:
        save_generated("学情分析", query, content)
    return ChainResult(content=content, citations=citations, data=data)

def _render(data: dict) -> str:
    def bullet(title, key):
        items = data.get(key) or []
        if not items:
            return f"**{title}**：暂无\n"
        return f"**{title}**：\n" + "\n".join(f"- {x}" for x in items) + "\n"

    return (
        "# 学情诊断\n\n"
        + bullet("高频错误", "high_freq_errors")
        + bullet("易混淆点", "confusions")
        + bullet("班级共性错误", "class_common_issues")
        + bullet("教学建议", "suggestions")
    )

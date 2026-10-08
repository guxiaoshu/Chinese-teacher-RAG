from __future__ import annotations

from ..retrieval.retriever import retrieve
from ..llm.deepseek import invoke_json
from ..ingestion.generated import save_generated
from .common import ChainResult, build_context, with_memory

_SYSTEM = """你是中学语文命题专家，为老师「针对学生真实踩坑点定制试卷」。

硬性规则：
1. 所有学生薄弱点、易混淆点必须来自检索到的【私有知识库】资料（历史错题/作答样本），不得凭空臆造。
2. 题目情境、易错选项直接参考往届学生真实错误作答；选择题干扰项优先使用学生真实错误答案。
3. 对照课标和教材校验，考点不得超纲。
4. 输出 JSON，结构如下（只输出 JSON，不要其它文字）：
{
  "title": "练习/试卷标题",
  "items": [
    {
      "type": "选择题",
      "question": "题干",
      "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
      "answer": "参考答案",
      "rubric": "评分细则",
      "rationale": "命题说明：对应学生哪一类典型问题（点明来自哪条错题）"
    }
  ],
  "overall_note": "总体说明（考情/适用对象/建议用时）"
}
"""

def run(query: str, save: bool = True, memory: str = "") -> ChainResult:
    docs = retrieve(query, library="private")
    ctx, citations = build_context(docs)
    user = with_memory(f"出题需求：{query}\n\n检索到的学生错题/作答样本（薄弱点必须来自这里）：\n{ctx}", memory)
    data = invoke_json([
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": user},
    ])
    content = _render(data)
    if save:
        save_generated("出题", query, content)
    return ChainResult(content=content, citations=citations, data=data)

def _render(data: dict) -> str:
    lines = [f"# {data.get('title', '')}"]
    for i, item in enumerate(data.get("items", []), 1):
        lines.append(f"\n## 第 {i} 题（{item.get('type', '')}）")
        lines.append(f"**题干**：{item.get('question', '')}")
        opts = item.get("options") or []
        if opts:
            lines.append("**选项**：" + "　".join(opts))
        lines.append(f"**参考答案**：{item.get('answer', '')}")
        lines.append(f"**评分细则**：{item.get('rubric', '')}")
        lines.append(f"**命题说明**：{item.get('rationale', '')}")
    if data.get("overall_note"):
        lines.append(f"\n---\n**总体说明**：{data['overall_note']}")
    return "\n".join(lines)

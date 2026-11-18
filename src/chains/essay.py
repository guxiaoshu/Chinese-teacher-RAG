from __future__ import annotations

from ..retrieval.retriever import retrieve
from ..llm.deepseek import invoke_json
from ..ingestion.composition import save_essay
from .common import ChainResult
from .essay_rubric import RUBRIC, level_of, level_name

_SYSTEM = f"""你是高考语文作文阅卷专家，严格执行下面的评分标准，给一篇学生作文精准评分分级。

{RUBRIC}

评分要求：
1. 只输出 JSON（不要输出其它任何文字），字段如下：
{{
  "content_score": 整数（0-20，内容分，须落在该作文所处档位区间内）,
  "expression_score": 整数（0-20，表达分）,
  "development_score": 整数（0-20，发展分）,
  "content_comment": "内容分项点评，一两句（与题意贴合度、中心、材料、思想感情）",
  "expression_comment": "表达分项点评，一两句（文体、结构、语言、书写）",
  "development_comment": "发展分项点评，一两句（深刻/丰富/有文采/有创意中的突出点或缺失）",
  "highlights": ["亮点1", "亮点2"],
  "problems": ["问题1", "问题2"],
  "suggestions": ["具体升格建议1", "具体升格建议2"],
  "overall_comment": "总体评语，两三句"
}}
2. 三个分项分数必须严格落在该作文实际达到档次的给分区间内，不得凭感觉乱给。
3. 若提供了该生过往作文，参考其水平轨迹，在 overall_comment 中指出进步或退步。
4. 若提供了范文锚点，与同题/同档范文对照校准给分。
5. 总分与档次由程序根据三项分自动计算，你无需输出总分和档次。
"""


def _score(v) -> int:
    try:
        return max(0, min(20, int(v)))
    except Exception:
        return 0


def _build_ref_context(past, refs) -> tuple[str, list[dict]]:
    parts: list[str] = []
    citations: list[dict] = []
    n = 0

    def add(docs, label):
        nonlocal n
        if not docs:
            return
        parts.append(f"【{label}】")
        for d in docs:
            n += 1
            parts.append(f"[{n}] 来源：{d.source_label()}｜类型：{d.doc_type}\n{d.text}")
            citations.append({"index": n, "source_file": d.source_file,
                              "library": d.library, "doc_type": d.doc_type})

    add(past, "该生过往作文（轨迹参考）")
    add(refs, "同题/同档范文锚点（校准参考）")
    ctx = "\n\n---\n\n".join(parts) if parts else "（暂无该生过往作文与范文，纯按评分标准打分）"
    return ctx, citations


def run(essay: str, student: str = "", topic: str = "", grade: str = "",
        save: bool = True) -> ChainResult:
    essay = (essay or "").strip()
    if not essay:
        return ChainResult(content="作文内容为空，请先粘贴或上传作文。", citations=[], data={})

    past = []
    if student:
        past = retrieve(essay, library="composition",
                        filters={"student": student, "doc_type": "学生作文"},
                        top_k=3, rewrite=False)
    q = topic or essay[:200]
    refs = retrieve(q, library="composition",
                    filters={"doc_type": "范文"}, top_k=3, rewrite=False)

    ctx, citations = _build_ref_context(past, refs)

    data = invoke_json([
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": f"作文题目：{topic or '（未提供）'}\n学生：{student or '（未提供）'}\n\n待批改作文全文：\n{essay}\n\n参考材料：\n{ctx}"},
    ], temperature=0.0)

    cs = _score(data.get("content_score"))
    es = _score(data.get("expression_score"))
    ds = _score(data.get("development_score"))
    total = cs + es + ds
    level = level_of(total)

    result = dict(data)
    result.update({
        "content_score": cs,
        "expression_score": es,
        "development_score": ds,
        "total": total,
        "level": level,
    })

    if save:
        save_essay(essay, student=student, topic=topic, level=level, score=total,
                   content_score=cs, expression_score=es, development_score=ds,
                   comment=data.get("overall_comment", ""), grade=grade)

    return ChainResult(content=_render(result), citations=citations, data=result)


def _render(d: dict) -> str:
    lines = [
        "# 作文批改",
        "",
        f"**总分**：{d.get('total', 0)} / 60　**档次**：{d.get('level', '')}（{level_name(d.get('level', ''))}）",
        "",
        "| 分项 | 得分 | 点评 |",
        "|---|---|---|",
        f"| 内容 | {d.get('content_score', 0)}/20 | {d.get('content_comment', '')} |",
        f"| 表达 | {d.get('expression_score', 0)}/20 | {d.get('expression_comment', '')} |",
        f"| 发展 | {d.get('development_score', 0)}/20 | {d.get('development_comment', '')} |",
    ]

    def bullet(title, key):
        items = d.get(key) or []
        if not items:
            return f"\n**{title}**：无"
        return f"\n**{title}**：\n" + "\n".join(f"- {x}" for x in items)

    lines.append(bullet("亮点", "highlights"))
    lines.append(bullet("问题", "problems"))
    lines.append(bullet("升格建议", "suggestions"))
    lines.append(f"\n**总体评语**：{d.get('overall_comment', '')}")
    return "\n".join(lines)

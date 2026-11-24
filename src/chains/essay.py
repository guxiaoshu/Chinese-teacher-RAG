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
  "total_score": 整数（0-60，总分，须落在该作文所处档位的给分区间内）,
  "content_comment": "内容点评，一两句（题意、立意、中心、材料、论据）",
  "expression_comment": "表达点评，一两句（文体、结构、语言、书写）",
  "development_comment": "发展点评，一两句（深刻/丰富/文采/创意中的突出点或缺失）",
  "highlights": ["亮点1", "亮点2"],
  "problems": ["问题1", "问题2"],
  "suggestions": ["具体升格建议1", "具体升格建议2"],
  "overall_comment": "总体评语，两三句"
}}
2. 总分必须严格落在该作文实际达到档次的给分区间内（A 50-60 / B 42-49 / C 30-41 / D 18-29 / E 0-17），不得凭感觉乱给。
3. 若提供了该生过往作文，参考其水平轨迹，在 overall_comment 中指出进步或退步。
4. 若提供了范文锚点（每篇已标注其档次 A-E），对照这些范文的水准来校准该作文的档次与总分。
5. 档次由程序根据总分自动计算，你无需输出档次。
"""


def _score(v, hi: int = 20) -> int:
    try:
        return max(0, min(hi, int(v)))
    except Exception:
        return 0
    # 做数值兜底钳位：转整数，限制 `[0, hi]`；这里调用传 hi=60，
    # 把 LLM 返回的总分锁死在 0–60；LLM 返回脏数据、非数字时兜底返回 0。


def _build_ref_context(past, refs) -> tuple[str, list[dict]]:#拼装批改参考上下文
#     两个来源：
# - `past`：该学生过往作文
# - `refs`：同主题范文锚点（top5）
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
            lv = (d.meta.get("level") or "").strip()
            tag = f"｜档次：{lv}（{level_name(lv)}）" if lv else ""
            parts.append(f"[{n}] 来源：{d.source_label()}｜类型：{d.doc_type}{tag}\n{d.text}")
            citations.append({"index": n, "source_file": d.source_file,
                              "library": d.library, "doc_type": d.doc_type,
                              "level": lv, "topic": (d.meta.get("topic") or ""),
                              "title": (d.meta.get("title") or "")})

    add(past, "该生过往作文（轨迹参考）")
    add(refs, "相似范文锚点（top-5 命中，按各自标注档次校准）")
    ctx = "\n\n---\n\n".join(parts) if parts else "（暂无该生过往作文与范文，纯按评分标准打分）"
    return ctx, citations


def run(essay: str, student: str = "", topic: str = "", grade: str = "", #批改主入口
        save: bool = True) -> ChainResult:
# - `essay`：待批改作文正文
# - `student`：学生标识（用来检索同一个人历史作文；不传就不查轨迹）
# - `topic`：作文题
# - `grade`：年级，入库元信息用
# - `save`：是否保存本次批改记录
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
                    filters={"doc_type": "范文"}, top_k=5, rewrite=False)

    ctx, citations = _build_ref_context(past, refs)

    data = invoke_json([
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": f"作文题目：{topic or '（未提供）'}\n学生：{student or '（未提供）'}\n\n待批改作文全文：\n{essay}\n\n参考材料：\n{ctx}"},
    ], temperature=0.0)

    total = _score(data.get("total_score"), hi=60)
    level = level_of(total)

    result = dict(data)
    result.update({
        "total": total,
        "level": level,
    })

    if save:
        save_essay(essay, student=student, topic=topic, level=level, score=total,
                   comment=data.get("overall_comment", ""), grade=grade)

    return ChainResult(content=_render(result), citations=citations, data=result)


def _render(d: dict) -> str:
    lines = [
        "# 作文批改",
        "",
        f"**总分**：{d.get('total', 0)} / 60　**档次**：{d.get('level', '')}（{level_name(d.get('level', ''))}）",
        "",
        f"**内容点评**：{d.get('content_comment', '')}",
        f"**表达点评**：{d.get('expression_comment', '')}",
        f"**发展点评**：{d.get('development_comment', '')}",
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

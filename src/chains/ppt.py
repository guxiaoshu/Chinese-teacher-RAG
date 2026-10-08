"""生成 PPT：检索教案/资料 → 大模型产出课件大纲 → 套模板或仿风格生成 .pptx。"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from ..retrieval.retriever import retrieve
from ..llm.deepseek import invoke_json
from ..ingestion.generated import save_generated
from ..config import BASE_DIR, PPT_OUTPUT_DIR
from ..ppt import engine
from .common import ChainResult, build_context

_SYSTEM = """你是一位资深中学语文教研员兼课件设计师。基于检索到的教案/资料，把一节课整理成结构清晰、可直接上屏的课件大纲。

硬性规则：
1. 只输出一个 JSON 对象，结构：{"title": "课件主标题", "subtitle": "副标题（可空字符串）", "slides": [{"title": "本页标题", "bullets": ["要点1", "要点2"]}]}
2. 第一层 title/subtitle 构成封面；slides 里每一项对应一页内容。
3. 内容页 6~10 页，每页 3~6 条要点，每条要点 ≤ 20 字，口语化、简洁、直接可读。
4. 页面标题要具体（如「一、作者与写作背景」），不要用泛泛的「内容」「正文」。
5. 内容来自参考材料、紧扣主题，不凭空编造；不输出任何 JSON 以外的文字。
"""


def run(query: str, template_slot: int | None = None, mode: str = "style",
        output_dir: str | None = None) -> ChainResult:
    docs = retrieve(query)
    ctx, citations = build_context(docs)

    data = invoke_json([
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": f"课件主题：{query}\n\n参考材料：\n{ctx}"},
    ], temperature=0.0)

    title = (str(data.get("title") or "").strip()) or (query.strip()[:40] or "课件")
    subtitle = str(data.get("subtitle") or "").strip()
    slides = [
        s for s in (data.get("slides") or [])
        if isinstance(s, dict) and (s.get("title") or "").strip()
    ]
    outline = {"title": title, "subtitle": subtitle, "slides": slides}

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_title = re.sub(r'[\\/:*?"<>|]', "", title)[:30] or "课件"
    filename = f"{safe_title}_{ts}.pptx"
    out_path = _resolve_out_dir(output_dir) / filename

    if mode == "fill":
        if not template_slot:
            raise ValueError("「直接套」需要先选择一个已放模板的槽位")
        tpl = engine.slot_path(int(template_slot))
        if not tpl.exists():
            raise ValueError("所选槽位还没有模板，请先上传模板或改用「仿风格」")
        engine.fill_template(tpl, outline, out_path)
    else:
        if template_slot and engine.slot_filled(int(template_slot)):
            style = engine.extract_style(engine.slot_path(int(template_slot)))
        else:
            style = engine.DEFAULT_STYLE
        engine.build_from_style(style, outline, out_path)

    preview = _render_preview(outline)
    save_generated("生成PPT", query, preview)

    return ChainResult(
        content=preview,
        citations=citations,
        data={
            "path": str(out_path),
            "filename": filename,
            "slides": len(slides),
            "mode": mode,
        },
    )


def _resolve_out_dir(output_dir: str | None) -> Path:
    if output_dir and output_dir.strip():
        p = Path(output_dir.strip())
        if not p.is_absolute():
            p = BASE_DIR / p
        p.mkdir(parents=True, exist_ok=True)
        return p
    return PPT_OUTPUT_DIR


def _render_preview(outline: dict) -> str:
    lines = [f"# {outline['title']}"]
    if outline.get("subtitle"):
        lines.append(f"*{outline['subtitle']}*")
    lines.append("")
    for i, s in enumerate(outline["slides"], 1):
        lines.append(f"## {i}. {s['title']}")
        for b in s.get("bullets", []):
            lines.append(f"- {b}")
        lines.append("")
    return "\n".join(lines)

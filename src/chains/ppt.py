"""生成 PPT：检索教案/资料 → 大模型产出课件大纲 → 智能设计引擎（多风格/多版式/真图/自检）或套模板。"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from ..retrieval.retriever import retrieve
from ..llm.deepseek import invoke_json
from ..ingestion.generated import save_generated
from ..config import BASE_DIR, PPT_OUTPUT_DIR
from ..ppt import deck, imagegen, styles
from .common import ChainResult, build_context

_SYSTEM = """你是一位资深中学语文教研员兼课件设计师。基于检索到的教案/资料，把一节课整理成结构清晰、可直接上屏的课件大纲。

硬性规则：
1. 只输出一个 JSON 对象，结构如下（slides 每项字段按需填写）：
{"title": "课件主标题", "subtitle": "副标题（可空字符串）", "slides": [
  {"title": "本页标题", "layout": "content|section|quote|compare|flow|closing",
   "quote": "原文金句（可空）", "bullets": ["要点"], "note": "一句讲解提示",
   "image_prompt": "一句配图描述",
   "compare": {"left": {"title":"","bullets":[]}, "right": {"title":"","bullets":[]}},
   "steps": ["环节1", "环节2"]}
]}
2. 第一层 title/subtitle 构成封面；slides 每一项对应一页。
3. 内容页 6~10 页；每页要点 3~5 条、每条 ≤ 14 字，精炼、直接可读。
4. layout 按内容选：对比/异同→compare，文脉/情节/步骤→flow，金句/原文诵读→quote，分课时/大板块→section，结尾收束→closing，其余→content。
5. 页面标题要具体、≤ 6 字（如「作者与背景」「写景顺序」「情感变化」），不要「内容」「正文」这类泛词。
6. quote 引原文关键句（没有则 ""）；note 写一句给老师的讲解提示；image_prompt 写一句中文配图描述，须包含「水墨、青绿山水、宣纸、留白、石潭、竹影、游鱼、光影」中若干元素。
7. compare 用于两栏对比（left/right 各含 title 和 bullets）；steps 用于横向流程，3~6 个环节。
8. 内容来自参考材料、紧扣主题，不凭空编造；不输出任何 JSON 以外的文字。
"""


def run(query: str, output_dir: str | None = None, save: bool = True,
        style_key: str | None = None, use_image: bool = True) -> ChainResult:
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

    style = styles.get(style_key) if style_key else styles.match_style(query)
    provider = imagegen.from_env() if use_image else None
    report = deck.build_deck(outline, style, out_path, image_provider=provider)

    preview = _render_preview(outline)
    if save:
        save_generated("生成PPT", query, preview)

    return ChainResult(
        content=preview,
        citations=citations,
        data={
            "path": str(out_path),
            "filename": filename,
            "slides": len(slides),
            "style": style.name,
            "used_image": provider is not None,
            "validate": len(report),
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
        layout = (s.get("layout") or "content").strip()
        lines.append(f"## {i}. {s['title']}  `[{layout}]`")
        quote = (s.get("quote") or "").strip()
        if quote:
            lines.append(f"> {quote}")
        for b in s.get("bullets", []):
            lines.append(f"- {b}")
        cmp = s.get("compare") or {}
        for side_name in ("left", "right"):
            side = cmp.get(side_name) or {}
            if side.get("title"):
                lines.append(f"  **{side['title']}**")
                for b in side.get("bullets", []):
                    lines.append(f"  - {b}")
        steps = s.get("steps") or []
        if steps:
            lines.append("  → " + " → ".join(steps))
        note = (s.get("note") or "").strip()
        if note:
            lines.append(f"_(讲：{note})_")
        lines.append("")
    return "\n".join(lines)

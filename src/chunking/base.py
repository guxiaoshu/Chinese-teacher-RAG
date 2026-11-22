from __future__ import annotations

import re
from dataclasses import dataclass, field

from langchain_text_splitters import RecursiveCharacterTextSplitter
#langchain-text-splitters；切分参数从全局配置 CONFIG["chunking"] 读取，方便统一调参。
from ..config import CONFIG
#优先按文档天然标题结构切，太长的段落再二次切碎，避免把一个完整知识点拦腰切断，提升 RAG 召回质量。
@dataclass
class Chunk:
    text: str  #切片文本
    meta: dict = field(default_factory=dict)#元数据（可以带上标题、前面 DocTags 的标签、source_hash、页码等）

def fallback_split(text: str) -> list[str]:
    # 兜底切分（递归字符切分）
    #这是经典的递归分割器，按优先级顺序尝试分隔符：
    #双换行 → 换行 → 句号 → 感叹号 → 问号 → 分号 → 逗号 → 空格 → 最后硬切
    #：一段没有标题、或者标题切出来的段落本身依然超长，就交给它切碎
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CONFIG["chunking"]["max_chunk_chars"],
        chunk_overlap=CONFIG["chunking"]["overlap_chars"],
        separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""],
    )
    return [t for t in splitter.split_text(text) if t.strip()]

def split_by_headings(text: str, patterns: list[str]) -> list[tuple[str, str]]:
    #按标题切分
    #用正则表达式匹配标题行，把原文切分成一组组
    lines = text.split("\n")
    compiled = [re.compile(p) for p in patterns]

    heading_idx: list[int] = []
    for i, line in enumerate(lines):
        s = line.strip()
        if s and any(c.match(s) for c in compiled):
            heading_idx.append(i)

    if not heading_idx:
        return [("", text.strip())]

    segments: list[tuple[str, str]] = []
    for j, idx in enumerate(heading_idx):
        start = idx
        end = heading_idx[j + 1] if j + 1 < len(heading_idx) else len(lines)
        heading = lines[idx].strip()
        body = "\n".join(lines[start:end]).strip()
        segments.append((heading, body))
    return segments

def _sub_split_long(body: str, max_chars: int | None = None) -> list[str]:
    #超长段落二次切分
    #标题切出来的这一节正文，如果长度没超上限 → 直接作为一个 chunk；
    #如果超长 → 调用 fallback_split 继续切碎。
    limit = max_chars or CONFIG["chunking"]["max_chunk_chars"]
    if len(body) <= limit:
        return [body]
    return fallback_split(body)

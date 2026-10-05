from __future__ import annotations

import re

from ..config import CONFIG
from .base import Chunk, fallback_split, split_by_headings

# 各种间隔号/中点：古文观止用 ‧、史记用 ·、庄子用 ・、全角 ．等
_SEP = "‧·．・"

# 古文观止 / 资治通鉴：卷X‧篇名；重编版另有「附录A/B‧篇名　作者」补篇
_VOLUME_RE = rf"^(?:卷[一二三四五六七八九十百千]+|附录[一二三四五六七八九十百千甲乙丙丁A-Za-z]+)[{_SEP}]"
# 世说新语 / 论语 / 孟子 / 史记 / 庄子：篇名第N，篇名可含间隔号
# 如「德行第一」「学而篇第一」「梁惠王上第一」「本纪·五帝本纪第一」「内篇・逍遥游第一」
_CHAPTER_RE = rf"^[一-鿿{_SEP}]{{2,15}}第[一二三四五六七八九十百]+$"
# 道德经：第一章 / 第二章 …
_NUM_CHAPTER_RE = r"^第[一二三四五六七八九十百]+章$"
# 世说新语条目：独立成行的「N.」
_ENTRY_RE = re.compile(r"^\d+[.、．]?$")


def _clean_title(s: str) -> str:
    return re.sub(r"[　\s]+", "·", s.strip()).strip("·")


def _drop_first_line(s: str) -> str:
    if "\n" in s:
        return s.split("\n", 1)[1].strip()
    return ""


def _split_entries(body: str) -> list[tuple[str, str]]:
    """按「N.」独立成行的条目拆开，返回 (条目号, 条目文本) 列表。"""
    entries: list[tuple[str, str]] = []
    cur_num, cur_buf = "", []
    for line in body.split("\n"):
        s = line.strip()
        if _ENTRY_RE.match(s):
            if cur_num or cur_buf:
                entries.append((cur_num, "\n".join(cur_buf).strip()))
            cur_num = s.rstrip(".、．")
            cur_buf = []
        else:
            cur_buf.append(line)
    if cur_num or cur_buf:
        entries.append((cur_num, "\n".join(cur_buf).strip()))
    return entries


class ClassicalTextChunker:
    """文言原著整部原文的切分器：按「卷/篇/条目」自然边界切，一篇(则)一块，不再硬切。"""

    doc_type = "文言原著"

    def split(self, text: str) -> list[Chunk]:
        # 归一化换行符：Windows 文本的 \r\n 会让 $ 锚点失配，统一转成 \n
        text = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        if not text:
            return []
        if re.search(_VOLUME_RE, text, re.M):
            return self._by_volume(text)
        if re.search(_CHAPTER_RE, text, re.M) or re.search(_NUM_CHAPTER_RE, text, re.M):
            return self._by_chapter(text)
        return [Chunk(text=t) for t in fallback_split(text)]

    def _by_volume(self, text: str) -> list[Chunk]:
        chunks: list[Chunk] = []
        for heading, body in split_by_headings(text, [_VOLUME_RE]):
            title = _clean_title(heading)
            body = body.strip()
            if title:
                body = _drop_first_line(body)
            if not body:
                continue
            if not title and len(body) < 12:
                continue  # 书名等孤立行
            chunks.extend(self._emit(title, body, {"篇目": title} if title else {}))
        return chunks

    def _by_chapter(self, text: str) -> list[Chunk]:
        chunks: list[Chunk] = []
        for chapter, body in split_by_headings(text, [_CHAPTER_RE, _NUM_CHAPTER_RE]):
            chapter = _clean_title(chapter)
            body = body.strip()
            if chapter:
                body = _drop_first_line(body)
            if not body:
                continue
            entries = _split_entries(body)
            if len(entries) > 1:
                for num, etxt in entries:
                    if not etxt:
                        continue
                    ctx = f"{chapter}·第{num}则" if chapter else f"第{num}则"
                    chunks.append(Chunk(text=f"{ctx}\n{etxt}", meta={"篇目": chapter, "条目": num}))
            else:
                if chapter:
                    chunks.extend(self._emit(chapter, body, {"篇目": chapter}))
                elif len(body) < 30:
                    continue  # 书名/作者等孤立头
                else:
                    chunks.extend(Chunk(text=t) for t in fallback_split(body))
        return chunks

    def _emit(self, title: str, body: str, meta: dict) -> list[Chunk]:
        limit = int(CONFIG["chunking"]["max_chunk_chars"])
        out: list[Chunk] = []
        if len(body) <= limit:
            out.append(Chunk(text=f"{title}\n{body}" if title else body, meta=meta))
        else:
            for sub in fallback_split(body):
                out.append(Chunk(text=f"{title}\n{sub}" if title else sub, meta=meta))
        return out

from __future__ import annotations

from .base import Chunk, split_by_headings, fallback_split
from .lesson_plan import LessonPlanChunker
from .wrong_answer import WrongAnswerChunker
from .classical import ClassicalChunker
from .composition import CompositionChunker

_CHUNKERS = {
    "教案": LessonPlanChunker(),
    "课堂笔记": LessonPlanChunker(),
    "学生错题": WrongAnswerChunker(),
    "学生作答样本": WrongAnswerChunker(),
    "习题": WrongAnswerChunker(),
    "文言笔记": ClassicalChunker(),
    "作文材料": CompositionChunker(),
}

def chunk_for(doc_type: str, text: str) -> list[Chunk]:
    chunker = _CHUNKERS.get(doc_type)
    if chunker is None:
        return [Chunk(text=t) for t in fallback_split(text)]
    return chunker.split(text)

__all__ = ["Chunk", "split_by_headings", "fallback_split", "chunk_for"]

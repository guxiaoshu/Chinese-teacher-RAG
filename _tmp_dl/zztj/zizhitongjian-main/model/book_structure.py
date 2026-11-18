"""
书籍结构模型：表示历史文本的层级结构

Book structure models representing the hierarchical organization of historical texts.
从 model.py 迁移而来，保持原有功能不变。
"""

import re
from dataclasses import dataclass, field
from typing import List
from pprint import pformat


PARA_IDX_PAT = re.compile(r"\[(\d+)\]")


@dataclass
class CmpStr:
    """
    对照字符串：存储原文和译文的对照
    
    Comparative string model storing original and translated text side by side.
    """
    original: str = field(default="")
    translated: str = field(default="")
    line_num: int = -1

    def check(self, **args):
        """验证原文和译文中的段落索引是否一致"""
        found = re.findall(PARA_IDX_PAT, self.original)
        if found:
            found_trans = re.findall(PARA_IDX_PAT, self.translated)
            assert (
                ("[todo]" in self.translated)
                or found_trans
                and (found[0] == found_trans[0])
            ), pformat([args, self, f"line {self.line_num}"])

        return True


@dataclass
class TimeSegment:
    """
    时间段落：以特定时间点开始的文本段落
    
    Time-based text segment starting with a specific timestamp.
    """
    start_time: CmpStr = field(default_factory=CmpStr)
    sentences: List[CmpStr] = field(default_factory=list)

    def check(self):
        """验证时间标记和所有句子的有效性"""
        assert re.findall(r"\d+", self.start_time.original) and re.findall(
            r"\d+", self.start_time.translated
        ), pformat(self.start_time)

        for s in self.sentences:
            s.check(time=self.start_time)

    def __str__(self):
        return f"小节-起始时间 {self.start_time.translated.split(' ')[-1]}，包含 {len(self.sentences)} 句"


@dataclass
class Chapter:
    """
    章节：对应资治通鉴的一卷
    
    Chapter model corresponding to one volume (卷) of the historical text.
    """
    index: int = field(default=-1)
    title: str = field(default="")
    segments: List[TimeSegment] = field(default_factory=list)

    def check(self):
        """验证章节标题包含'卷'字"""
        assert "卷" in self.title, pformat(self.title)

    def __str__(self):
        return f"{self.title}（包含{len(self.segments)}小节）"


@dataclass
class Book:
    """
    书籍：完整的历史文本
    
    Complete book model containing all chapters.
    """
    chapters: List[Chapter] = field(default_factory=list)
    
    def __str__(self):
        return f"资治通鉴（共{len(self.chapters)}卷）"
    
    def get_chapter(self, index: int) -> Chapter | None:
        """根据索引获取章节"""
        for chapter in self.chapters:
            if chapter.index == index:
                return chapter
        return None
    
    def get_segment(self, chapter_index: int, segment_index: int) -> TimeSegment | None:
        """根据章节索引和段落索引获取特定段落"""
        chapter = self.get_chapter(chapter_index)
        if chapter and 0 <= segment_index < len(chapter.segments):
            return chapter.segments[segment_index]
        return None


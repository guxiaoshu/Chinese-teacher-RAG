"""
资治通鉴数据处理脚本

从Markdown文件中提取和构建书籍结构数据。
使用 model.book_structure 中定义的数据模型。
"""

import re
import json
import os
from dataclasses import asdict
from typing import List
from glob import glob
from pprint import pformat

from tqdm import tqdm

from model.book_structure import Book, Chapter, TimeSegment, CmpStr, PARA_IDX_PAT

files = glob("chapters/*.md")
cur_file = None


# Load the JSON file and convert back to Python objects
def json_to_book(file_path: str) -> Book:
    def cmpstr_from_dict(data):
        return CmpStr(**data)

    def timesegment_from_dict(data):
        return TimeSegment(
            start_time=cmpstr_from_dict(data["start_time"]),
            sentences=[cmpstr_from_dict(s) for s in data["sentences"]],
        )

    def chapter_from_dict(data):
        return Chapter(
            index=data["index"],
            title=data["title"],
            segments=[timesegment_from_dict(s) for s in data["segments"]],
        )

    def book_from_dict(data):
        return Book(chapters=[chapter_from_dict(c) for c in data["chapters"]])

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return book_from_dict(data)

if __name__ == "__main__":
    book = Book()
    pbar = tqdm(files)
    for f in pbar:
        cur_file = f
        pbar.set_description(f)
        lines = open(f, "r").readlines()
        chapter = Chapter()
        chapter.title = lines[0].strip("\n")
        chapter.index = int(f.split(os.sep)[-1].split("_")[0])
        i = 1
        # lines_bar = tqdm(total=len(lines))
        # lines_bar.update(1)
        while i < len(lines):
            line = lines[i]
            if line == "\n":
                i += 1
                continue
            if not line.startswith("\u3000\u3000"):
                ts = TimeSegment()
                ts.start_time = CmpStr(line.strip(), lines[i + 2].strip(), i)
                ts.check()
                i += 3
                while i < len(lines):
                    # lines_bar.update(i - lines_bar.n)
                    line = lines[i]
                    if line == "\n":
                        i += 1
                    elif not line.startswith("\u3000\u3000"):
                        i -= 1
                        break
                    elif line != "\n":
                        ts.sentences.append(CmpStr(line.strip(), lines[i + 2].strip(), i))
                        ts.sentences[-1].check(time=ts.start_time)
                        i += 3
                    else:
                        raise RuntimeError(lines[i])
                ts.check()
                chapter.segments.append(ts)
            else:
                raise RuntimeError(lines[i : i + 5])
            # lines_bar.update(i - lines_bar.n)

        book.chapters.append(chapter)

    book.chapters.sort(key=lambda x: x.index)
    json.dump(
        asdict(book), open("data.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False
    )

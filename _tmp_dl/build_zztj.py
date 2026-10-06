# -*- coding: utf-8 -*-
"""从 JY0284/zizhitongjian 的 data.json 抽取「文言原文」，拼成卷-年份结构的完整 txt。

卷标题格式对齐切分器的 _VOLUME_RE：`卷{中文数字}·{纪名}{序}`，如「卷一·周纪一」。
源数据两个坑：①「秦记」是「秦纪」的错字；②「汉纪—」的「—」是「一」的异写。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

SRC = Path("zztj/zizhitongjian-main/data.json")
OUT = Path("../ingest/public/资治通鉴.txt")

_DIGITS = "零一二三四五六七八九"
_DASHES = "—―－‐–-"  # 各种连字符，按「一」处理


def cn_num(n: int) -> str:
    """1~999 的整数转中文数字，如 294 -> 二百九十四。

    注意只能用「一二三四五六七八九十百千」，不能出现「零/〇」
    （切分器的 _VOLUME_RE 只认这组字，105 写作「一百五」、113 写作「一百一十三」）。
    """
    if n < 10:
        return _DIGITS[n]
    if n < 100:
        tens, ones = divmod(n, 10)
        return ("" if tens == 1 else _DIGITS[tens]) + "十" + (_DIGITS[ones] if ones else "")
    # 100~999
    hundreds, rest = divmod(n, 100)
    s = _DIGITS[hundreds] + "百"
    if rest:
        tens, ones = divmod(rest, 10)
        if tens:
            s += _DIGITS[tens] + "十"  # 含 tens==1 时也要「一十」，如 113 -> 一百一十三
            if ones:
                s += _DIGITS[ones]
        else:
            s += _DIGITS[ones]
    return s


def clean_sentence(s: str) -> str:
    s = re.sub(r"^\s*\[\d+\]\s*", "", s).strip()
    return s


def split_heading(first_orig: str) -> tuple[str | None, str]:
    """从卷首年份行拆出「纪名+序」与剩余年份行。

    如「周纪一 威烈王二十三年(…)」-> ("周纪一", "威烈王二十三年(…)" )
       「唐纪二高祖…武德元年(…)」    -> ("唐纪二", "高祖…武德元年(…)" )
       「安皇帝戊元興二年(…)」        -> (None, 原样)   # 无纪名，如卷113/200
    """
    m = re.match(r"^([^　\s]{1,4}?[纪记])([一二三四五六七八九十〇零" + _DASHES + r"]+)\s*", first_orig)
    if m:
        name = m.group(1).replace("记", "纪")
        seq = "".join("一" if c in _DASHES else c for c in m.group(2))
        seq = seq.replace("〇", "零")
        return name + seq, first_orig[m.end():].strip()
    return None, first_orig.strip()


def title_jiname(title: str) -> str:
    """从 title 括号里取纪名（如「(后周纪)」-> 后周纪），并修正「秦记」。"""
    m = re.search(r"[（(]([^）)]+)[）)]", title)
    return (m.group(1).strip().replace("记", "纪") if m else "")


def main() -> None:
    data = json.loads(SRC.read_text(encoding="utf-8"))
    chapters = data["chapters"]
    print(f"章节数: {len(chapters)}")

    out: list[str] = []
    total_chars = 0
    for ch in chapters:
        idx = int(ch["index"])
        segs = ch["segments"]
        first_orig = segs[0]["start_time"]["original"]
        name_seq, year0 = split_heading(first_orig)
        if name_seq:
            heading = f"卷{cn_num(idx)}·{name_seq}"
        else:
            heading = f"卷{cn_num(idx)}·{title_jiname(ch['title'])}"
        out.append(heading)
        for j, seg in enumerate(segs):
            st = seg["start_time"]["original"]
            year = year0 if j == 0 else st.strip()
            out.append(year)
            for s in seg["sentences"]:
                t = clean_sentence(s["original"])
                if t:
                    out.append(t)
                    total_chars += len(t)
        out.append("")  # 卷间空行

    text = "\n".join(out).strip() + "\n"
    OUT.write_text(text, encoding="utf-8")
    print(f"输出: {OUT}  ({len(text)} 字符 / {total_chars} 正文字符)")
    print("--- 开头 200 字 ---")
    print(text[:200])
    print("--- 结尾 120 字 ---")
    print(text[-120:])


if __name__ == "__main__":
    main()

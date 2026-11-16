# -*- coding: utf-8 -*-
"""去掉 Python 文件里的 # 注释（保留字符串/docstring/代码结构/空白）。"""
import sys
import io
import tokenize
from pathlib import Path


def strip_comments(source: str) -> str:
    out = []
    prev_row, prev_col = 1, 0
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type == tokenize.COMMENT:
            continue
        row, col = tok.start
        if row > prev_row:
            out.append('\n' * (row - prev_row))
            prev_col = 0
        if col > prev_col:
            out.append(' ' * (col - prev_col))
        out.append(tok.string)
        prev_row, prev_col = tok.end
    text = ''.join(out)
    return '\n'.join(line.rstrip() for line in text.split('\n'))


def main():
    for t in sys.argv[1:]:
        p = Path(t)
        src = p.read_text(encoding='utf-8')
        stripped = strip_comments(src)
        p.write_text(stripped, encoding='utf-8')
        print(f'已清除注释: {p.name}  ({len(src)} -> {len(stripped)} 字符)')


if __name__ == '__main__':
    main()

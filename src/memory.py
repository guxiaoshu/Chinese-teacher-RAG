"""手动长期记忆：老师希望助手长期记住的上下文，存一个纯文本文件。

网页右侧的「希望我记住什么？」框读写这里。生成时作为高优先级的长期上下文
注入到 写教案/出题/答疑/学情分析 四条链路（作文批改不读取）。
"""
from __future__ import annotations

from .config import DATA_DIR

_PATH = DATA_DIR / "remember.txt"


def load() -> str:
    if _PATH.exists():
        return _PATH.read_text(encoding="utf-8")
    return ""


def save(text: str) -> None:
    _PATH.write_text((text or "").strip(), encoding="utf-8")

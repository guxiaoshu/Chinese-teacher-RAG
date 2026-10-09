"""会话记录持久化：把各功能的多轮「需求 → 结果」记录落到磁盘。

之前这些记录只存在 st.session_state 里，一旦刷新页面、服务重启、或浏览器
断线重连（局域网多人用很容易发生），全部记录就没了。这里把历史写到
data/history/ 下的 JSON 文件，启动时读回 session_state，追加时写回，
切换功能、刷新、重启都不丢。
"""
from __future__ import annotations

import json
from pathlib import Path

from .config import DATA_DIR

_DIR = DATA_DIR / "history"

# 有会话记录的功能：session_state key → 显示名（顺序即前端 tab 顺序）
FEATURES = {
    "hist_lp": "写教案",
    "hist_exam": "出题",
    "hist_qa": "答疑",
    "hist_la": "学情分析",
}


def _path(key: str) -> Path:
    return _DIR / f"{key}.json"


def load(key: str) -> list[dict]:
    """读取某功能的历史记录；文件不存在或损坏时返回空列表。"""
    p = _path(key)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def save(key: str, rounds: list[dict]) -> None:
    """把某功能的历史记录整体写盘（前端追加一轮后传全量列表）。

    磁盘写失败不抛异常，避免影响正常生成流程。
    """
    try:
        _DIR.mkdir(parents=True, exist_ok=True)
        _path(key).write_text(
            json.dumps(rounds, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


def clear(key: str) -> None:
    """清空某功能的历史记录（内存 + 磁盘）。"""
    p = _path(key)
    try:
        p.unlink(missing_ok=True)
    except Exception:
        pass

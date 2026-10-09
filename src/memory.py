"""手动长期记忆：老师希望助手长期记住的上下文。

网页右侧的「希望我记住什么？」框读写这里。生成时作为高优先级的长期上下文
注入到 写教案/出题/答疑/学情分析 四条链路（作文批改不读取）。

框下方 4 个开关决定这段记忆分别对哪条链路生效（点亮的才注入），
文字与生效范围一起持久化到 remember.json；旧版 remember.txt 保留纯文本兜底。
"""
from __future__ import annotations

import json

from .config import DATA_DIR

_PATH = DATA_DIR / "remember.txt"
_JSON_PATH = DATA_DIR / "remember.json"

# 会读取长期记忆的四条链路，顺序即前端按钮顺序
SCOPES = ["写教案", "出题", "答疑", "学情分析"]


def _read_text() -> str:
    """读取记忆正文：新格式优先，旧版纯文本兜底。"""
    if _JSON_PATH.exists():
        try:
            data = json.loads(_JSON_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("text"), str):
                return data["text"].strip()
        except Exception:
            pass
    if _PATH.exists():
        return _PATH.read_text(encoding="utf-8").strip()
    return ""


def load() -> dict:
    """返回 {text: str, scopes: list[str]}；旧格式没有 scopes 时默认四条链路全生效。"""
    scopes = list(SCOPES)
    if _JSON_PATH.exists():
        try:
            data = json.loads(_JSON_PATH.read_text(encoding="utf-8"))
            s = data.get("scopes")
            if isinstance(s, list):
                scopes = [x for x in SCOPES if x in s]
        except Exception:
            pass
    return {"text": _read_text(), "scopes": scopes}


def save(text: str, scopes: list[str] | None = None) -> None:
    """保存记忆正文与生效链路（scopes 缺省视为全选）。"""
    data = {
        "text": (text or "").strip(),
        "scopes": [x for x in (scopes or SCOPES) if x in SCOPES],
    }
    _JSON_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    # 同步一份纯文本，兼容任何仍直接读 remember.txt 的旧路径
    _PATH.write_text(data["text"], encoding="utf-8")

from __future__ import annotations

import threading
from pathlib import Path

from ..config import BASE_DIR, CONFIG

_R = CONFIG["retrieval"]

_model = None
_lock = threading.Lock()


def _model_path() -> str:
    p = str(_R.get("rerank_model") or "").strip()
    if not p:
        return ""
    path = Path(p)
    if not path.is_absolute():
        path = BASE_DIR / path
    return str(path.resolve())


def available() -> bool:
    """模型文件是否就绪（只查文件、不加载模型，避免每次检索都先拉起模型）。"""
    root = Path(_model_path())
    if not (root / "config.json").exists():
        return False
    return (root / "model.safetensors").exists() or (root / "pytorch_model.bin").exists()


def _load():
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                from sentence_transformers import CrossEncoder

                _model = CrossEncoder(_model_path(), max_length=512)
    return _model


def rerank(query: str, texts: list[str]) -> list[float]:
    """返回 texts 与 query 的相关度分数（越大越相关），顺序与输入一致。"""
    if not texts:
        return []
    model = _load()
    scores = model.predict(
        [(query, t) for t in texts],
        batch_size=16,
        show_progress_bar=False,
        convert_to_numpy=True,
    )
    return [float(s) for s in scores]

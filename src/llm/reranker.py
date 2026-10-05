from __future__ import annotations

import threading
from typing import Sequence

import torch

from ..config import CONFIG

_RERANK = CONFIG.get("rerank", {})
_MODEL_NAME = str(_RERANK.get("model_name", "BAAI/bge-reranker-v2-m3"))
_MAX_LEN = int(_RERANK.get("max_length", 512))
_BATCH = int(_RERANK.get("batch_size", 16))

_model = None
_tokenizer = None
_device = None
_load_failed = False
_lock = threading.Lock()


def _load():
    """懒加载 cross-encoder 重排模型。失败一次则本进程内不再重试，避免每次查询都卡在下载。"""
    global _model, _tokenizer, _device, _load_failed
    if _model is None and not _load_failed:
        with _lock:
            if _model is None and not _load_failed:
                try:
                    from transformers import AutoModelForSequenceClassification, AutoTokenizer

                    _device = "cuda" if torch.cuda.is_available() else "cpu"
                    _tokenizer = AutoTokenizer.from_pretrained(_MODEL_NAME)
                    _model = AutoModelForSequenceClassification.from_pretrained(_MODEL_NAME)
                    _model.to(_device)
                    _model.eval()
                except Exception:
                    _load_failed = True
                    _model = None
                    _tokenizer = None
                    _device = None
    return _model, _tokenizer, _device


def available() -> bool:
    return _load()[0] is not None


def rerank(query: str, docs: Sequence[str]) -> list[float]:
    """对 query 与每个 doc 的相关性打分（cross-encoder 精排）。

    返回与 docs 等长的分数列表（[0,1]）；模型不可用时返回全 0，由调用方降级到 RRF 顺序。
    """
    if not docs:
        return []
    model, tok, device = _load()
    if model is None:
        return [0.0] * len(docs)

    scores: list[float] = []
    for i in range(0, len(docs), _BATCH):
        batch = list(docs[i : i + _BATCH])
        enc = tok(
            [[query, d] for d in batch],
            padding=True,
            truncation=True,
            max_length=_MAX_LEN,
            return_tensors="pt",
        )
        enc = {k: v.to(device) for k, v in enc.items()}
        with torch.no_grad():
            logits = model(**enc).logits.view(-1).float()
        scores.extend(torch.sigmoid(logits).cpu().tolist())
    return scores

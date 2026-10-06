from __future__ import annotations

import threading

import torch
import torch.nn.functional as F
from transformers import AutoModel, AutoTokenizer

from ..config import CONFIG

_MODEL_NAME = CONFIG["embedding"]["model_name"]
_QUERY_INSTRUCTION = CONFIG["embedding"]["query_instruction"]
_MAX_LEN = 512
_BATCH_SIZE = 32

_model = None
_tokenizer = None
_device = None
_lock = threading.Lock()

def _load():
    global _model, _tokenizer, _device
    if _model is None:
        with _lock:
            if _model is None:
                try:
                    torch.set_num_threads(max(1, min(4, (torch.get_num_threads() or 4))))
                except Exception:
                    pass
                _device = "cuda" if torch.cuda.is_available() else "cpu"
                # 优先离线读本地缓存，避免每次启动先联网探测（离线环境会卡几秒）；缓存缺失才联网下载
                try:
                    _tokenizer = AutoTokenizer.from_pretrained(_MODEL_NAME, local_files_only=True)
                    _model = AutoModel.from_pretrained(_MODEL_NAME, local_files_only=True)
                except Exception:
                    _tokenizer = AutoTokenizer.from_pretrained(_MODEL_NAME)
                    _model = AutoModel.from_pretrained(_MODEL_NAME)
                _model = _model.to(_device)
                _model.eval()
                _enc = _tokenizer(["预热"], padding=True, truncation=True, return_tensors="pt")
                _enc = {k: v.to(_device) for k, v in _enc.items()}
                with torch.no_grad():
                    _model(**_enc)
    return _model, _tokenizer, _device

def _encode(texts: list[str], normalize: bool = True):
    model, tok, device = _load()
    enc = tok(texts, padding=True, truncation=True, max_length=_MAX_LEN, return_tensors="pt")
    enc = {k: v.to(device) for k, v in enc.items()}
    with torch.no_grad():
        out = model(**enc)
    cls = out.last_hidden_state[:, 0]
    if normalize:
        cls = F.normalize(cls, p=2, dim=1)
    return cls.cpu().numpy()

def embed_documents(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    results: list[list[float]] = []
    for i in range(0, len(texts), _BATCH_SIZE):
        batch = texts[i : i + _BATCH_SIZE]
        results.extend(_encode(batch, normalize=True).tolist())
    return results

def embed_query(text: str) -> list[float]:
    return _encode([_QUERY_INSTRUCTION + text], normalize=True).tolist()[0]

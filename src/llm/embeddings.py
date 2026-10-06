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
                # 长文本由 _encode_one 自行滑窗，先抬高 tokenizer 的长度阈值，避免取原始 ids 时刷屏警告
                _tokenizer.model_max_length = 4096
                _model = _model.to(_device)
                _model.eval()
                _enc = _tokenizer(["预热"], padding=True, truncation=True, return_tensors="pt")
                _enc = {k: v.to(_device) for k, v in _enc.items()}
                with torch.no_grad():
                    _model(**_enc)
    return _model, _tokenizer, _device

def _encode_one(model, tok, device, text: str):
    """单条编码：≤512 token 直接 [CLS]；超长则滑窗切分、各窗 [CLS] 取均值。

    bge-base-zh 上限 512 token，而文言切片可达 ~1200 字（≈1190 token），
    直接截断会丢掉后半段（对向量检索不可见）。滑窗 + 均值池化让整段都参与向量。
    """
    ids = tok(text, add_special_tokens=False, truncation=False)["input_ids"]
    content_max = _MAX_LEN - 2  # 预留 [CLS] / [SEP]
    if len(ids) <= content_max:
        enc = tok(text, padding=True, truncation=True, max_length=_MAX_LEN, return_tensors="pt")
        enc = {k: v.to(device) for k, v in enc.items()}
        with torch.no_grad():
            out = model(**enc)
        return out.last_hidden_state[:, 0]

    cls_id = tok.cls_token_id
    sep_id = tok.sep_token_id
    pad_id = tok.pad_token_id if tok.pad_token_id is not None else 0
    step = content_max - 64  # 相邻窗口重叠 64 token，避免语义被切断
    windows: list[list[int]] = []
    for i in range(0, len(ids), step):
        w = ids[i : i + content_max]
        if len(w) < 16:
            continue
        windows.append([cls_id] + w + [sep_id])
    if not windows:
        windows = [[cls_id] + ids[:content_max] + [sep_id]]

    cls_vecs = []
    for i in range(0, len(windows), _BATCH_SIZE):
        batch = windows[i : i + _BATCH_SIZE]
        padded = torch.nn.utils.rnn.pad_sequence(
            [torch.tensor(w, dtype=torch.long) for w in batch],
            batch_first=True, padding_value=pad_id)
        attn = (padded != pad_id).long()
        enc = {"input_ids": padded.to(device), "attention_mask": attn.to(device)}
        with torch.no_grad():
            out = model(**enc)
        cls_vecs.append(out.last_hidden_state[:, 0])
    return torch.cat(cls_vecs, dim=0).mean(dim=0, keepdim=True)


def _encode(texts: list[str], normalize: bool = True):
    model, tok, device = _load()
    vecs = [_encode_one(model, tok, device, t) for t in texts]
    out = torch.cat(vecs, dim=0)
    if normalize:
        out = F.normalize(out, p=2, dim=1)
    return out.cpu().numpy()

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

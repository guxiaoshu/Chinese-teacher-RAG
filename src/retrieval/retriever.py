from __future__ import annotations

import threading
from dataclasses import dataclass, field

import jieba
from rank_bm25 import BM25Okapi

from ..config import CONFIG, authority_weight_map
from ..llm.embeddings import embed_query
from ..vectorstore.store import LIBRARY_COLLECTION, get_all_documents, get_collection
from .query_rewrite import rewrite_query

_R = CONFIG["retrieval"]
_AUTHORITY = authority_weight_map()

_index: dict[str, dict] = {}
_index_lock = threading.Lock()

@dataclass
class RetrievedDoc:
    text: str
    meta: dict
    score: float
    library: str
    source_file: str = ""
    doc_type: str = ""
    chunk_id: str = ""

    def source_label(self) -> str:
        lib = "私有知识库" if self.library == "private" else "公共基准库"
        return f"【{lib}】{self.source_file}"

def _tokenize(text: str) -> list[str]:
    return [t for t in jieba.lcut(text) if t.strip()]

def rebuild_index(library: str | None = None) -> None:
    libs = [library] if library else list(LIBRARY_COLLECTION.keys())
    for lib in libs:
        data = get_all_documents(lib)
        ids = data.get("ids") or []
        texts = data.get("documents") or []
        metas = data.get("metadatas") or []
        tokenized = [_tokenize(t) for t in texts]
        bm25 = BM25Okapi(tokenized) if tokenized else None
        with _index_lock:
            _index[lib] = {"ids": ids, "texts": texts, "metas": metas,
                           "tokenized": tokenized, "bm25": bm25}

def _ensure_index(library: str) -> dict:
    if library not in _index:
        rebuild_index(library)
    return _index[library]

def _to_where(filters: dict | None) -> dict | None:
    if not filters:
        return None
    where = {}
    for k, v in filters.items():
        if v not in (None, ""):
            where[k] = {"$eq": str(v)}
    return where or None

def _matches(meta: dict, filters: dict | None) -> bool:
    if not filters:
        return True
    for k, v in filters.items():
        if v in (None, ""):
            continue
        if str(meta.get(k, "")) != str(v):
            return False
    return True

def _vector_rank(library: str, query: str, filters: dict | None, n: int) -> list[str]:
    emb = embed_query(query)
    col = get_collection(library)
    res = col.query(query_embeddings=[emb], n_results=max(n, 1), where=_to_where(filters))
    ids = res.get("ids") or [[]]
    return [i for i in ids[0] if i]

def _bm25_rank(library: str, query: str, filters: dict | None, n: int) -> list[str]:
    idx = _ensure_index(library)
    bm25 = idx.get("bm25")
    if bm25 is None:
        return []
    scores = bm25.get_scores(_tokenize(query))
    order = sorted(range(len(scores)), key=lambda i: -scores[i])
    out = []
    for i in order:
        if scores[i] <= 0:
            break
        if not _matches(idx["metas"][i], filters):
            continue
        out.append(idx["ids"][i])
        if len(out) >= n:
            break
    return out

def _rrf(rankings: list[list[str]], k: int) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda x: -x[1])

def _retrieve_single(library: str, query: str, filters: dict | None, top_k: int) -> list[RetrievedDoc]:
    n = max(top_k, _R["bm25_top_k"], _R["private_top_k"], _R["public_top_k"])
    vec_ids = _vector_rank(library, query, filters, n)
    bm_ids = _bm25_rank(library, query, filters, n)

    ranked = _rrf([vec_ids, bm_ids], _R["rrf_k"])

    idx = _ensure_index(library)
    id_map = {idx["ids"][i]: i for i in range(len(idx["ids"]))}

    results: list[RetrievedDoc] = []
    for doc_id, rrf_score in ranked:
        pos = id_map.get(doc_id)
        if pos is None:
            continue
        meta = idx["metas"][pos]
        text = idx["texts"][pos]
        authority = meta.get("authority", "其他")
        weight = _AUTHORITY.get(authority, 1)
        final_score = rrf_score + weight * _R["authority_boost"]
        results.append(RetrievedDoc(
            text=text,
            meta=meta,
            score=final_score,
            library=library,
            source_file=meta.get("source_file", ""),
            doc_type=meta.get("doc_type", ""),
            chunk_id=doc_id,
        ))
        if len(results) >= top_k:
            break
    return results

def retrieve(query: str, library: str | None = None, filters: dict | None = None,
             top_k: int | None = None, rewrite: bool = True) -> list[RetrievedDoc]:
    if rewrite:
        query = rewrite_query(query)

    if library in ("private", "public"):
        k = top_k or (_R["private_top_k"] if library == "private" else _R["public_top_k"])
        return _retrieve_single(library, query, filters, k)

    k_priv = top_k or _R["private_top_k"]
    k_pub = _R["public_top_k"]
    priv = _retrieve_single("private", query, filters, k_priv)
    pub = _retrieve_single("public", query, filters, k_pub)
    return priv + pub

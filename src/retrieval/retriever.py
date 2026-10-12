from __future__ import annotations

import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import jieba
from rank_bm25 import BM25Okapi

from ..config import CONFIG, authority_weight_map, api_key_ready, allowed_grades
from ..llm.embeddings import embed_query, embed_documents
from ..llm.deepseek import invoke_json
from ..vectorstore.store import LIBRARY_COLLECTION, get_all_documents, get_collection, upsert_chunks
from .query_rewrite import expand_queries, extract_intent
from . import reranker

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
        labels = {"private": "私有知识库", "public": "公共基准库", "composition": "作文库"}
        lib = labels.get(self.library, "知识库")
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
        tokenized = [_tokenize(contextualize(t, m or {})) for t, m in zip(texts, metas)]
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
    conds = [{k: {"$eq": str(v)}} for k, v in filters.items() if v not in (None, "")]
    if not conds:
        return None
    if len(conds) == 1:
        return conds[0]
    # chroma 顶层 where 只能有一个操作符，多字段过滤用 $and 包裹
    return {"$and": conds}

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


def _meta_list(meta: dict, key: str) -> list[str]:
    """Chroma 把 list 元数据存成了 JSON 字符串，这里统一解析成 list。"""
    v = meta.get(key)
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x) for x in v]
    if isinstance(v, str):
        try:
            parsed = json.loads(v)
        except Exception:
            return [v]
        if isinstance(parsed, list):
            return [str(x) for x in parsed]
        return [v]
    return [str(v)]


def contextualize(text: str, meta: dict) -> str:

    if not _R.get("contextualize", True):
        return text
    meta = meta or {}
    article = (meta.get("article") or "").strip()
    grade = (meta.get("grade") or "").strip()
    kps = _meta_list(meta, "knowledge_points")[:3]
    parts = []
    if article:
        parts.append(f"篇目：{article}")
    if grade:
        parts.append(f"学段：{grade}")
    if kps:
        parts.append("知识点：" + "、".join(kps))
    if not parts:
        return text
    return "【" + "】【".join(parts) + "】" + text


_GRADE_RE = re.compile("|".join(re.escape(g) for g in allowed_grades()))


def _regex_intent(query: str) -> dict:

    article = ""
    m = re.search(r"《([^》]{1,30})》", query)
    if m:
        article = m.group(1).strip()
    grade = ""
    gm = _GRADE_RE.search(query)
    if gm:
        grade = gm.group(0)
    return {"article": article, "grade": grade, "knowledge_points": [], "doc_type": ""}


def _metadata_boost(meta: dict, intent: dict) -> float:

    if not intent:
        return 0.0
    score = 0.0
    article = (intent.get("article") or "").strip()
    grade = (intent.get("grade") or "").strip()
    kps = intent.get("knowledge_points") or []

    if article:
        meta_article = (meta.get("article") or "").strip()
        if meta_article and meta_article == article:
            score += 0.5
        elif meta_article and article in meta_article:
            score += 0.2
    if grade and (meta.get("grade") or "") == grade:
        score += 0.15
    if kps:
        overlap = len(set(kps) & set(_meta_list(meta, "knowledge_points")))
        if overlap:
            score += 0.1 * overlap
    return score


def _recall_candidates(library: str, query: str, filters: dict | None, n: int, intent: dict) -> list[RetrievedDoc]:
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
        # AI 自动沉淀的内容（generated=True）一律按最低权威，避免"模型读自己上次输出"的自我强化
        if meta.get("generated"):
            weight = 1
        final_score = rrf_score * (1 + (weight - 1) * _R["authority_boost"])
        if _R.get("use_metadata_boost"):
            final_score += _metadata_boost(meta, intent)
        results.append(RetrievedDoc(
            text=text,
            meta=meta,
            score=final_score,
            library=library,
            source_file=meta.get("source_file", ""),
            doc_type=meta.get("doc_type", ""),
            chunk_id=doc_id,
        ))
    results.sort(key=lambda d: -d.score)
    return results


def _recall_library(library: str, queries: list[str], filters: dict | None, top_k: int, intent: dict) -> list[RetrievedDoc]:
    n = max(top_k, _R["bm25_top_k"], _R.get("rerank_candidates", 20))
    merged: dict[str, RetrievedDoc] = {}
    for q in queries:
        for d in _recall_candidates(library, q, filters, n, intent):
            if d.chunk_id in merged:
                # 多个变体都命中 → 取更高分并加一个命中加成
                merged[d.chunk_id].score = max(merged[d.chunk_id].score, d.score) + 0.05
            else:
                merged[d.chunk_id] = d
    return sorted(merged.values(), key=lambda d: -d.score)


_RERANK_SYSTEM = """你是检索结果精排器。给定用户问题和若干候选文本片段（每片有编号），做两件事：
1. 按与问题的语义相关性从高到低排序。
2. 判断每片与问题「相关」（能帮助回答/备课该问题）还是「无关」（主题无关，即使个别词重合也不算相关）。
只输出 JSON：{"rank": [编号...], "relevant": [相关编号...]}。rank 按相关性降序、必须包含所有编号；relevant 是 rank 的子集，只放真正相关的编号。不要输出其它文字。"""


def _llm_rerank(query: str, docs: list[RetrievedDoc]) -> list[RetrievedDoc]:

    if len(docs) <= 1:
        return docs
    items = []
    for i, d in enumerate(docs):
        text = re.sub(r"\s+", " ", d.text)[:600]
        items.append(f"[{i}] {text}")
    prompt = f"问题：{query}\n\n候选片段：\n" + "\n".join(items)
    try:
        raw = invoke_json([
            {"role": "system", "content": _RERANK_SYSTEM},
            {"role": "user", "content": prompt},
        ], temperature=0.0)
        order = raw.get("rank") or []
        # 按原始编号重排，保留 (原始编号, doc) 以支持相关度过滤
        reordered: list[tuple[int, RetrievedDoc]] = []
        seen: set[int] = set()
        for x in order:
            try:
                i = int(x)
            except Exception:
                continue
            if 0 <= i < len(docs) and i not in seen:
                reordered.append((i, docs[i]))
                seen.add(i)
        for i, d in enumerate(docs):
            if i not in seen:
                reordered.append((i, d))
        # 相关度过滤：模型明确给了 relevant 字段就按它过滤（空列表 = 全部无关，丢弃）；
        # 字段缺失才视为未判定，全保留（优雅降级）。
        relevant_field = raw.get("relevant")
        if relevant_field is not None:
            rel_set: set[int] = set()
            for x in relevant_field:
                try:
                    rel_set.add(int(x))
                except Exception:
                    continue
            reordered = [(i, d) for i, d in reordered if i in rel_set]
        return [d for _, d in reordered]
    except Exception:
        return docs


_CROSS_AUTHORITY_COEFF = 0.03  # 交叉编码器精排后，权威仅作轻微乘性加成；主排序由语义相关度决定


def _cross_rerank(query: str, docs: list[RetrievedDoc]) -> list[RetrievedDoc]:

    if len(docs) <= 1:
        return docs
    # 精排只看片段开头（标题/首句通常已含主题），且 bge-reranker 注意力是 O(n²)，
    # 截到 256 字符能比 450 字符快 3 倍左右，CPU 上才扛得住全量评测。
    texts = [re.sub(r"\s+", " ", d.text)[:256] for d in docs]
    try:
        scores = reranker.rerank(query, texts)
    except Exception:
        return docs  # 模型缺失/加载失败时降级：保留 RRF 原序
    for d, s in zip(docs, scores):
        auth_w = _AUTHORITY.get(d.meta.get("authority", "其他"), 1)
        d.score = s * (1 + (auth_w - 1) * _CROSS_AUTHORITY_COEFF)
    docs.sort(key=lambda d: -d.score)
    return docs


def _jaccard(a: str, b: str) -> float:
    sa = set(_tokenize(a))
    sb = set(_tokenize(b))
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _dedup(docs: list[RetrievedDoc], threshold: float) -> list[RetrievedDoc]:
    if not threshold or threshold <= 0 or len(docs) <= 1:
        return docs
    kept: list[RetrievedDoc] = []
    kept_sets: list[set] = []
    for d in docs:
        s = set(_tokenize(d.text))
        if any(len(s & ks) / max(len(s | ks), 1) >= threshold for ks in kept_sets):
            continue
        kept.append(d)
        kept_sets.append(s)
    return kept


def _rerank(query: str, docs: list[RetrievedDoc], top_k: int, enabled: bool) -> list[RetrievedDoc]:
    threshold = float(_R.get("dedup_similarity", 0) or 0)
    if not (enabled and len(docs) > top_k):
        return _dedup(docs, threshold)[:top_k]
    top_n = min(_R.get("rerank_candidates", 20), len(docs))
    if _R.get("rerank_backend", "cross_encoder") == "llm":
        ordered = _llm_rerank(query, docs[:top_n])
    else:
        ordered = _cross_rerank(query, docs[:top_n])
    return _dedup(ordered, threshold)[:top_k]


def retrieve(query: str, library: str | None = None, filters: dict | None = None,
             top_k: int | None = None, rewrite: bool | None = None) -> list[RetrievedDoc]:
    # rewrite=None 时读 config 的 retrieval.rewrite（默认关）：false 走纯向量+BM25+RRF 快速路径。
    if rewrite is None:
        rewrite = bool(_R.get("rewrite", True))
    # 查询扩展与意图解析是两个独立的 LLM 往返，串行会白白叠加网络延迟；
    # 并行发起，等待从「求和」变成「取最长」。带缓存，重复提问仍走 lru_cache。
    if rewrite:
        with ThreadPoolExecutor(max_workers=2) as ex:
            f_queries = ex.submit(expand_queries, query)
            use_intent = bool(_R.get("use_metadata_boost")) and api_key_ready()
            f_intent = ex.submit(extract_intent, query) if use_intent else None
            queries = f_queries.result()
            intent = f_intent.result() if f_intent else {}
    else:
        queries = [query]
        # 快速模式下仍用正则抽《篇目》/学段做元数据加权，不额外调 LLM
        intent = _regex_intent(query) if _R.get("use_metadata_boost") else {}

    backend = _R.get("rerank_backend", "cross_encoder")
    if backend == "llm":
        do_rerank = rewrite and bool(_R.get("rerank")) and api_key_ready()
    elif backend == "none":
        do_rerank = False
    else:
        # 交叉编码器本地推理、无 LLM 往返，快速路径（rewrite=False）也启用精排
        do_rerank = bool(_R.get("rerank")) and reranker.available()

    if library in ("private", "public", "composition"):
        k = top_k or (_R["private_top_k"] if library == "private" else _R["public_top_k"])
        docs = _recall_library(library, queries, filters, k, intent)
        return _rerank(query, docs, k, do_rerank)

    k_priv = top_k or _R["private_top_k"]
    k_pub = _R["public_top_k"]
    priv = _recall_library("private", queries, filters, k_priv, intent)
    pub = _recall_library("public", queries, filters, k_pub, intent)
    # 两个库的精排互不依赖（纯 LLM 调用），并行发起；召回（向量+BM25）保持串行，避免并发碰共享 embedding/Chroma。
    with ThreadPoolExecutor(max_workers=2) as ex:
        f_priv = ex.submit(_rerank, query, priv, k_priv, do_rerank)
        f_pub = ex.submit(_rerank, query, pub, k_pub, do_rerank)
        priv = f_priv.result()
        pub = f_pub.result()
    # 私有库加权后与公共库合并排序（private_weight > 1 表示私有优先）
    pw = float(_R.get("private_weight", 1.0))
    for d in priv:
        d.score *= pw
    merged = sorted(priv + pub, key=lambda d: -d.score)
    return merged[:top_k] if top_k else merged


def reembed_library(library: str | None = None) -> int:

    libs = [library] if library else list(LIBRARY_COLLECTION.keys())
    total = 0
    for lib in libs:
        data = get_all_documents(lib)
        ids = data.get("ids") or []
        texts = data.get("documents") or []
        metas = data.get("metadatas") or []
        if not ids:
            continue
        embs = embed_documents([contextualize(t, m or {}) for t, m in zip(texts, metas)])
        upsert_chunks(lib, ids, texts, embs, metas)
        rebuild_index(lib)
        total += len(ids)
    return total

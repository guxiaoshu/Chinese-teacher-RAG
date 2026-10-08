from __future__ import annotations

import hashlib
import re
from datetime import datetime

from ..config import CONFIG, DATA_DIR
from ..tagging.classifier import DocTags
from ..chunking import chunk_for
from ..llm.embeddings import embed_documents
from ..vectorstore.store import upsert_chunks
from ..retrieval.retriever import rebuild_index

_SCENARIO_TO_TYPE = {
    "写教案": "教案",
    "出题": "习题",
    "答疑": "课堂笔记",
    "学情分析": "课堂笔记",
}

_AUTHORITY = {
    # AI 自动沉淀的内容不再挂「教师教案」高权威，否则会和老师真实手写教案同权重竞争；
    # 统一按「其他」最低权威，检索时还可再靠 meta.generated 进一步降权。
    "教案": "其他",
    "课堂笔记": "其他",
    "习题": "其他",
}

_GENERATED_DIR = DATA_DIR / "generated"

def _extract_article(query: str) -> str:
    m = re.search(r"《([^》]{1,30})》", query)
    return m.group(1).strip() if m else ""

def _prepare(scenario: str, query: str, content: str):
    """把生成内容切成切片并备好元数据（不落库）。返回 (doc_type, source_name, sha, meta_common, chunks)。"""
    content = (content or "").strip()
    if not content:
        return None
    doc_type = _SCENARIO_TO_TYPE.get(scenario, "其他")
    tags = DocTags(
        doc_type=doc_type,
        article=_extract_article(query),
        summary=content.split("\n")[0][:100],
    )
    chunks = chunk_for(doc_type, content)
    if not chunks:
        return None

    sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    source_name = f"生成-{scenario}-{ts}.md"
    meta_common = {
        "source_file": source_name,
        "source_path": str(_GENERATED_DIR / source_name),
        "source_hash": sha,
        "library": "private",
        "doc_type": doc_type,
        "grade": tags.grade,
        "unit": tags.unit,
        "article": tags.article,
        "knowledge_points": tags.knowledge_points,
        "learning_tags": tags.learning_tags,
        "situation_note": tags.situation_note,
        "summary": tags.summary,
        "authority": _AUTHORITY.get(doc_type, "其他"),
        "generated": True,
        "scenario": scenario,
    }
    return doc_type, source_name, sha, meta_common, chunks


def _commit(meta_common: dict, chunks, selected: set | None) -> int:
    """把（选中的）切片嵌入并写入私有库，重建索引。返回入库切片数。"""
    ids, texts, metas = [], [], []
    for i, c in enumerate(chunks):
        if selected is not None and i not in selected:
            continue
        if not c.text.strip():
            continue
        ids.append(f"gen-{meta_common['source_hash'][:16]}-{i}")
        texts.append(c.text)
        meta = dict(meta_common)
        meta.update(c.meta)
        meta["chunk_index"] = i
        metas.append(meta)
    if not texts:
        return 0
    embs = embed_documents(texts)
    upsert_chunks("private", ids, texts, embs, metas)
    rebuild_index("private")
    return len(texts)


def _write_source_file(scenario: str, query: str, content: str, source_name: str) -> None:
    _GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    header = (
        f"# {scenario}（手动入库）\n\n"
        f"> 需求：{query}\n"
        f"> 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    )
    (_GENERATED_DIR / source_name).write_text(header + content, encoding="utf-8")


def save_generated(scenario: str, query: str, content: str) -> bool:
    """整段入库（原自动沉淀路径；受 config 的 auto_save_generated 控制）。"""
    if not CONFIG.get("ingestion", {}).get("auto_save_generated", True):
        return False
    prepared = _prepare(scenario, query, content)
    if prepared is None:
        return False
    _, source_name, _, meta_common, chunks = prepared
    try:
        n = _commit(meta_common, chunks, None)
        if n:
            _write_source_file(scenario, query, content, source_name)
        return n > 0
    except Exception:
        return False


def preview_generated_chunks(scenario: str, query: str, content: str) -> dict:
    """把生成内容切成切片，返回给前端逐个勾选：{sha, chunks: [{index, text, doc_type}]}。"""
    prepared = _prepare(scenario, query, content)
    if prepared is None:
        return {"sha": "", "chunks": []}
    _, _, sha, _, chunks = prepared
    return {
        "sha": sha,
        "chunks": [
            {"index": i, "text": c.text.strip(), "doc_type": c.meta.get("doc_type", "")}
            for i, c in enumerate(chunks) if c.text.strip()
        ],
    }


def save_generated_selected(scenario: str, query: str, content: str, selected) -> bool:
    """只入库被勾选的切片（selected 为切片 index 列表）。手动动作，不受 auto_save_generated 影响。"""
    prepared = _prepare(scenario, query, content)
    if prepared is None:
        return False
    _, source_name, _, meta_common, chunks = prepared
    try:
        n = _commit(meta_common, chunks, set(selected or []))
        if n:
            _write_source_file(scenario, query, content, source_name)
        return n > 0
    except Exception:
        return False

from __future__ import annotations

from pathlib import Path


from .config import PRIVATE_DIR, PUBLIC_DIR
from .ingestion.loader import extract_text, is_supported
from .ingestion.state import (
    init_db,
    sha256_of,
    file_status,
    get_sha,
    mark_processed,
    mark_error,
    mark_skipped,
)
from .tagging.classifier import classify
from .chunking import chunk_for
from .llm.embeddings import embed_documents
from .vectorstore.store import upsert_chunks, delete_by_source_hash
from .retrieval.retriever import rebuild_index

def detect_library(path: Path | str) -> str:
    rp = Path(path).resolve()
    try:
        if rp.is_relative_to(PUBLIC_DIR.resolve()):
            return "public"
    except Exception:
        pass
    return "private"

def _hint_dir(path: Path, library: str) -> str:
    base = PRIVATE_DIR if library == "private" else PUBLIC_DIR
    try:
        return str(path.parent.resolve().relative_to(base.resolve()))
    except Exception:
        return ""

def _authority_for(tags, chunk_meta: dict) -> str:
    if chunk_meta.get("批注"):
        return "教师批注"
    dt = tags.doc_type
    if dt in ("教案", "课堂笔记"):
        return "教师教案"
    if dt in ("学生错题", "学生作答样本", "作文材料"):
        return "学生作答"
    if dt == "文言笔记":
        return "教参"
    if dt == "习题":
        return "其他"
    return "其他"

def build_meta(path: Path, library: str, sha: str, tags, chunk_meta: dict, idx: int) -> dict:
    meta = {
        "source_file": path.name,
        "source_path": str(path),
        "source_hash": sha,
        "library": library,
        "doc_type": tags.doc_type,
        "grade": tags.grade,
        "unit": tags.unit,
        "article": tags.article,
        "knowledge_points": tags.knowledge_points,
        "learning_tags": tags.learning_tags,
        "situation_note": tags.situation_note,
        "summary": tags.summary,
        "authority": _authority_for(tags, chunk_meta),
        "chunk_index": idx,
    }
    meta.update(chunk_meta)
    return meta

def process_file(path: Path | str) -> dict:
    init_db()
    p = Path(path)
    if not p.exists():
        return {"path": str(p), "status": "missing"}
    if not is_supported(p):
        return {"path": str(p), "status": "unsupported"}

    sha = sha256_of(p)
    library = detect_library(p)
    st = file_status(p, sha)
    if st == "processed":
        return {"path": str(p), "status": "skipped", "reason": "已入库且内容未变"}

    old_sha = get_sha(p)
    if old_sha and old_sha != sha:
        try:
            delete_by_source_hash(library, old_sha)
        except Exception:
            pass

    try:
        text = extract_text(p)
        if not text or not text.strip():
            mark_skipped(p, sha, library)
            return {"path": str(p), "status": "skipped", "reason": "文档无文本层（可能是扫描版 PDF）"}

        tags = classify(text, filename=p.name, hint_dir=_hint_dir(p, library))
        chunks = chunk_for(tags.doc_type, text)
        if not chunks:
            mark_error(p, sha, library, "切片结果为空")
            return {"path": str(p), "status": "error", "error": "切片结果为空"}

        ids, texts, metas = [], [], []
        for i, c in enumerate(chunks):
            if not c.text.strip():
                continue
            ids.append(f"{sha}-{i}")
            texts.append(c.text)
            metas.append(build_meta(p, library, sha, tags, c.meta, i))

        embs = embed_documents(texts)
        upsert_chunks(library, ids, texts, embs, metas)
        rebuild_index(library)
        mark_processed(p, sha, library, len(texts), tags.doc_type, tags.to_metadata())
        return {"path": str(p), "status": "processed", "chunks": len(texts), "doc_type": tags.doc_type}
    except Exception as e:
        mark_error(p, sha, library, str(e))
        return {"path": str(p), "status": "error", "error": str(e)}

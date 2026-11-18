from __future__ import annotations

import hashlib
from datetime import datetime

from ..config import COMPOSITION_DIR
from ..llm.embeddings import embed_documents
from ..vectorstore.store import get_collection, upsert_chunks
from ..retrieval.retriever import rebuild_index


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _exists(sha: str) -> bool:
    try:
        res = get_collection("composition").get(where={"source_hash": sha}, include=["documents"])
        return bool(res.get("ids"))
    except Exception:
        return False


def _upsert(text: str, meta: dict, prefix: str) -> bool:
    """作文库专用入库：全文作为一个 Chunk，不进入通用 public/private 流程。"""
    text = (text or "").strip()
    if not text:
        return False
    sha = _sha(text)
    if _exists(sha):
        return False
    COMPOSITION_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    name = f"{prefix}-{ts}-{sha[:8]}.md"
    p = COMPOSITION_DIR / name
    p.write_text(text, encoding="utf-8")

    meta = dict(meta)
    meta.update({
        "source_file": name,
        "source_path": str(p),
        "source_hash": sha,
        "library": "composition",
    })
    emb = embed_documents([text])
    upsert_chunks("composition", [f"comp-{sha[:16]}"], [text], emb, [meta])
    rebuild_index("composition")
    return True


def save_essay(text: str, *, student: str, topic: str, level: str,
               score: int, content_score: int, expression_score: int,
               development_score: int, comment: str, grade: str = "") -> bool:
    """沉淀一篇已批改的学生作文（含评分与点评）。"""
    return _upsert(text, {
        "doc_type": "学生作文",
        "student": student or "",
        "topic": topic or "",
        "grade": grade or "",
        "level": level,
        "score": int(score),
        "content_score": int(content_score),
        "expression_score": int(expression_score),
        "development_score": int(development_score),
        "comment": comment or "",
    }, "essay")


def import_reference(text: str, *, topic: str, level: str, title: str = "") -> bool:
    """导入范文作评分锚点，档次（A-E）由老师手动指定。"""
    return _upsert(text, {
        "doc_type": "范文",
        "topic": topic or "",
        "title": title or "",
        "level": level,
    }, "reference")

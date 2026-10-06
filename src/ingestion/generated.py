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

def save_generated(scenario: str, query: str, content: str) -> bool:
    if not CONFIG.get("ingestion", {}).get("auto_save_generated", True):
        return False
    content = (content or "").strip()
    if not content:
        return False
    try:
        doc_type = _SCENARIO_TO_TYPE.get(scenario, "其他")
        tags = DocTags(
            doc_type=doc_type,
            article=_extract_article(query),
            summary=content.split("\n")[0][:100],
        )
        chunks = chunk_for(doc_type, content)
        if not chunks:
            return False

        sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        source_name = f"生成-{scenario}-{ts}.md"

        ids, texts, metas = [], [], []
        for i, c in enumerate(chunks):
            if not c.text.strip():
                continue
            ids.append(f"gen-{sha[:16]}-{i}")
            texts.append(c.text)
            meta = {
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
                "chunk_index": i,
            }
            meta.update(c.meta)
            metas.append(meta)

        embs = embed_documents(texts)
        upsert_chunks("private", ids, texts, embs, metas)
        rebuild_index("private")

        _GENERATED_DIR.mkdir(parents=True, exist_ok=True)
        header = (
            f"# {scenario}（自动沉淀）\n\n"
            f"> 需求：{query}\n"
            f"> 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        )
        (_GENERATED_DIR / source_name).write_text(header + content, encoding="utf-8")
        return True
    except Exception:
        return False

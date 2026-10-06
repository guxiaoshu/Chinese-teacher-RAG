from __future__ import annotations

import json

from ..config import CHROMA_DIR

LIBRARY_COLLECTION = {"public": "public_base", "private": "private_kb"}

_client = None
_collections: dict[str, object] = {}

def get_client():
    global _client
    if _client is None:
        import chromadb

        _client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return _client

def get_collection(library: str):
    if library not in LIBRARY_COLLECTION:
        raise ValueError(f"未知库类型: {library}")
    if library not in _collections:
        _collections[library] = get_client().get_or_create_collection(
            LIBRARY_COLLECTION[library], metadata={"hnsw:space": "cosine"}
        )
    return _collections[library]

def _flatten_meta(meta: dict) -> dict:
    out: dict = {}
    for k, v in meta.items():
        if v is None:
            out[k] = ""
        elif isinstance(v, (list, dict)):
            out[k] = json.dumps(v, ensure_ascii=False)
        elif isinstance(v, bool):
            out[k] = v
        elif isinstance(v, (int, float)):
            out[k] = v
        else:
            out[k] = str(v)
    return out

def upsert_chunks(library: str, ids: list[str], texts: list[str],
                  embeddings: list[list[float]], metas: list[dict]) -> None:
    col = get_collection(library)
    flat_metas = [_flatten_meta(m) for m in metas]
    # chroma 单次 upsert 有上限（约 5461），大文件（如资治通鉴近万切片）分批写入
    batch = 5000
    for i in range(0, len(ids), batch):
        col.upsert(
            ids=ids[i : i + batch],
            documents=texts[i : i + batch],
            embeddings=embeddings[i : i + batch],
            metadatas=flat_metas[i : i + batch],
        )

def delete_by_source_hash(library: str, source_hash: str) -> None:
    col = get_collection(library)
    col.delete(where={"source_hash": source_hash})

def get_all_documents(library: str) -> dict:
    col = get_collection(library)
    return col.get(include=["documents", "metadatas"])

def count_documents(library: str | None = None) -> dict[str, int]:
    libs = [library] if library else list(LIBRARY_COLLECTION.keys())
    return {lib: get_collection(lib).count() for lib in libs}

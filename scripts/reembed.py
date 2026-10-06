# -*- coding: utf-8 -*-
"""把库里已有的切片用当前 embedding 实现重新向量化。

改过 embedding 算法（如长文本滑窗池化）后跑一次，让旧切片也吃上新算法。
文本/元数据不变，只替换 embedding，BM25 索引无需重建。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.llm.embeddings import embed_documents
from src.vectorstore.store import get_all_documents, upsert_chunks


def main() -> None:
    for lib in ("public", "private"):
        data = get_all_documents(lib)
        ids = data.get("ids") or []
        texts = data.get("documents") or []
        metas = data.get("metadatas") or []
        if not ids:
            print(f"[{lib}] 空库，跳过")
            continue
        t0 = time.time()
        print(f"[{lib}] 重新向量化 {len(ids)} 个切片…")
        embs = embed_documents(texts)
        upsert_chunks(lib, ids, texts, embs, metas)
        print(f"[{lib}] 完成，耗时 {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()

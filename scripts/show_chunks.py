"""查看切片：按文件名或库，打印已入库切片的内容与元数据。

用法（在项目根目录）：
    python scripts/show_chunks.py                 # 列出每个文件的切片数
    python scripts/show_chunks.py 论语            # 打印文件名含"论语"的所有切片全文
    python scripts/show_chunks.py 论语 --lib public --limit 5
    python scripts/show_chunks.py 史记 五帝       # 文件名含"史记"，且正文含"五帝"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.vectorstore.store import get_all_documents, count_documents  # noqa: E402


def _rows(library: str):
    data = get_all_documents(library)
    docs = data.get("documents") or []
    metas = data.get("metadatas") or []
    for i, doc in enumerate(docs):
        meta = metas[i] if i < len(metas) else {}
        yield i, doc, meta


def main() -> None:
    ap = argparse.ArgumentParser(description="查看已入库切片")
    ap.add_argument("name", nargs="?", default="", help="文件名关键词（含即可）")
    ap.add_argument("--lib", choices=["public", "private", "all"], default="all")
    ap.add_argument("--limit", type=int, default=0, help="最多打印几条（0=全部）")
    ap.add_argument("--text", default="", help="正文关键词，进一步筛选")
    ap.add_argument("--no-text", action="store_true", help="只打印元数据，不打印正文")
    args = ap.parse_args()

    libs = ["public", "private"] if args.lib == "all" else [args.lib]

    if not args.name:
        print("=== 各库各文件切片数 ===")
        for lib in libs:
            counts: dict[str, int] = {}
            for _, _, meta in _rows(lib):
                key = f"{lib} / {meta.get('source_file', '?')} / {meta.get('doc_type', '?')}"
                counts[key] = counts.get(key, 0) + 1
            for key, n in sorted(counts.items()):
                print(f"  {n:4d}  {key}")
        print(f"\n公共库 {count_documents('public')['public']} · 私有库 {count_documents('private')['private']}")
        return

    shown = 0
    for lib in libs:
        for i, doc, meta in _rows(lib):
            fname = str(meta.get("source_file", ""))
            if args.name and args.name not in fname:
                continue
            if args.text and args.text not in doc:
                continue
            shown += 1
            if args.limit and shown > args.limit:
                return
            print("=" * 70)
            print(f"[{shown}] {lib} · {fname} · {meta.get('doc_type')} · 切片#{meta.get('chunk_index')}")
            for k in ("篇目", "article", "unit", "authority", "knowledge_points", "summary"):
                v = meta.get(k)
                if v:
                    print(f"    {k}: {v}")
            if not args.no_text:
                print("-" * 70)
                print(doc.strip())
                print("-" * 70)


if __name__ == "__main__":
    main()

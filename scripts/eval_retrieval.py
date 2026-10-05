from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.retrieval.retriever import retrieve

_EVAL_PATH = Path(__file__).resolve().parent.parent / "data" / "eval_set.json"

def load_eval() -> tuple[int, list[dict]]:
    with open(_EVAL_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return int(data.get("k", 5)), data["queries"]

def _is_relevant(doc, item: dict) -> bool:
    expect_text = item.get("expect_text")
    if expect_text:
        return all(k in doc.text for k in expect_text)
    expected = item.get("expected", [])
    source = doc.source_file or ""
    article = doc.meta.get("article", "") or ""
    return any(k in source or k in article for k in expected)

def _eval_once(queries: list[dict], k: int, rewrite: bool) -> dict:
    recall_hits = 0
    mrr_total = 0.0
    details: list[dict] = []
    for item in queries:
        q = item["query"]
        docs = retrieve(q, library="public", top_k=k, rewrite=rewrite)
        rank = None
        for i, d in enumerate(docs, 1):
            if _is_relevant(d, item):
                rank = i
                break
        hit = rank is not None
        if hit:
            recall_hits += 1
            mrr_total += 1.0 / rank
        details.append({"query": q, "hit": hit, "rank": rank,
                        "top1": docs[0].source_file if docs else "(无)"})
    n = len(queries)
    return {
        "recall_at_k": recall_hits / n if n else 0.0,
        "mrr": mrr_total / n if n else 0.0,
        "hits": recall_hits,
        "total": n,
        "details": details,
    }

def _print(result: dict, label: str, k: int) -> None:
    print(f"\n===== {label}（k={k}）=====")
    print(f"Recall@{k}: {result['recall_at_k']:.2%}  ({result['hits']}/{result['total']})")
    print(f"MRR:        {result['mrr']:.3f}")

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--on", action="store_true", help="只跑改写开启")
    ap.add_argument("--off", action="store_true", help="只跑改写关闭")
    args = ap.parse_args()

    k, queries = load_eval()
    print(f"评估集共 {len(queries)} 条，k={k}")

    if args.on or args.off:
        rewrite = args.on
        _print(_eval_once(queries, k, rewrite), "Query 改写 开启" if rewrite else "Query 改写 关闭", k)
    else:
        off = _eval_once(queries, k, rewrite=False)
        on = _eval_once(queries, k, rewrite=True)
        _print(off, "Query 改写 关闭", k)
        _print(on, "Query 改写 开启", k)
        print("\n--- 改写带来的变化 ---")
        for old, new in zip(off["details"], on["details"]):
            if old["hit"] != new["hit"]:
                arrow = "✅ 命中" if new["hit"] else "❌ 丢失"
                print(f"  {arrow}: {new['query'][:30]} (关→{old['top1']}, 开→{new['top1']})")

if __name__ == "__main__":
    main()

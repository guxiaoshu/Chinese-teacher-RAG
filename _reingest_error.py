# -*- coding: utf-8 -*-
"""一次性：清理旧 Desktop 记录 + 重新入库 error 文件"""
import sys
from pathlib import Path

PROJECT = Path(r'E:\Chinese-teacher---RAG\Chinese-teacher---RAG')
sys.path.insert(0, str(PROJECT))

from src.ingestion.state import get_conn, clear_record, sha256_of
from src.pipeline import process_file, detect_library
from src.vectorstore.store import delete_by_source_hash
from src.retrieval.retriever import rebuild_index

# 1. 清理旧 Desktop 残留记录
conn = get_conn()
n = conn.execute("DELETE FROM files WHERE path LIKE ?", (r'C:\Users\BEIYU\Desktop\rag-teacher%',)).rowcount
conn.commit()
conn.close()
print(f"[1/3] 已清理 {n} 条旧 Desktop 记录", flush=True)

# 2. 找出 error 文件
conn = get_conn()
rows = conn.execute("SELECT path FROM files WHERE status='error'").fetchall()
conn.close()
error_paths = [Path(r[0]) for r in rows]
print(f"[2/3] 需要重新入库 {len(error_paths)} 个 error 文件", flush=True)

# 3. 逐个清旧状态 + 重新入库（rebuild=False，最后统一建索引）
for i, p in enumerate(error_paths, 1):
    print(f"  [{i}/{len(error_paths)}] {p.name}", flush=True)
    if not p.exists():
        print("    文件不存在，跳过", flush=True)
        continue
    try:
        lib = detect_library(p)
        sha = sha256_of(p)
        delete_by_source_hash(lib, sha)  # 清掉可能残留的旧切片
        clear_record(p)  # 清掉 SQLite 旧记录
        r = process_file(p, rebuild=False)  # 重新入库
        print(f"    结果: {r.get('status')} 切片 {r.get('chunks', 0)}", flush=True)
    except Exception as e:
        print(f"    失败: {e}", flush=True)

# 4. 统一重建索引
print("[3/3] 重建索引...", flush=True)
rebuild_index()
print("全部完成", flush=True)

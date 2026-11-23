from __future__ import annotations

import threading
from pathlib import Path
#RAG 文档入库主流程

from .config import PRIVATE_DIR, PUBLIC_DIR
from .ingestion.loader import extract_text, is_supported
# extract_text：PDF/Word等抽取文本；is_supported：判断后缀是否支持
from .ingestion.state import (
    init_db,       # 初始化本地sqlite状态库，记录文件：路径、sha、处理状态、错误信息
    sha256_of,     # 文件sha256哈希，用来判断文件有没有改动
    file_status,   # 查询当前文件+哈希组合的状态：processed / error / skipped
    get_sha,       # 根据文件路径查上一次入库的哈希
    mark_processed, mark_error, mark_skipped # 写状态库，标记结果
)
from .tagging.classifier import classify
# 核心：LLM分类器，读文本+文件名+目录提示，输出结构化tags：doc_type/年级/单元/知识点等
from .chunking import chunk_for
# 根据文档类型(doc_type)走不同分片策略：文言原著、教案、习题、作文，切块规则不一样
from .llm.embeddings import embed_documents
# 就是上一段你发的embedding模块，批量生成文档向量
from .vectorstore.store import upsert_chunks, delete_by_source_hash
# 向量库层：写入分片；按source_hash删除旧分片（文件更新时清理旧向量）
from .retrieval.retriever import rebuild_index, contextualize
# rebuild_index：向量库索引重建；contextualize：分片文本增强（RAG常用，给chunk加上下文摘要再embedding

# 入库会用到共享的 embedding 模型 / tokenizer / ChromaDB，用全局锁串行化，避免并发竞态
_INGEST_LOCK = threading.Lock()

def detect_library(path: Path | str) -> str:
    #判断属于 public /private 库
    rp = Path(path).resolve()
    try:
        if rp.is_relative_to(PUBLIC_DIR.resolve()):
            return "public"
    except Exception:
        pass
    return "private"

def _hint_dir(path: Path, library: str) -> str:
    #拿到这个文件相对于库根目录的**相对路径字符串**，传给 `classify` 打标签做提示。
    base = PRIVATE_DIR if library == "private" else PUBLIC_DIR
    try:
        return str(path.parent.resolve().relative_to(base.resolve()))
    except Exception:
        return ""

def _authority_for(tags, chunk_meta: dict) -> str:
    #教育场景权重字段
    #生成 `authority` 可信度字段，检索时可以用来做排序 / 过滤
    if chunk_meta.get("批注"):
        return "教师批注"
    dt = tags.doc_type
    if dt in ("教案", "课堂笔记"):
        return "教师教案"
    if dt in ("学生错题", "学生作答样本", "作文材料"):
        return "学生作答"
    if dt == "文言原著":
        return "教材"
    if dt == "文言笔记":
        return "教参"
    if dt == "习题":
        return "其他"
    return "其他"

def build_meta(path: Path, library: str, sha: str, tags, chunk_meta: dict, idx: int) -> dict:
   #构建分片元数据 meta
   #每一个 chunk 都会带上全套元信息，存在向量库里面，检索返回时一起带出
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

def process_file(path: Path | str, rebuild: bool = True) -> dict:
    #入参 `rebuild=True`：入库完成后是否重建向量索引
    #主函数
    init_db()
    p = Path(path)
    if not p.exists():
        return {"path": str(p), "status": "missing"}
    if not is_supported(p):
        return {"path": str(p), "status": "unsupported"}
    #先检查文件是否存在、后缀是否支持（docx、pdf、md 等）
    sha = sha256_of(p)
    library = detect_library(p)
    st = file_status(p, sha)
    if st == "processed":
        return {"path": str(p), "status": "skipped", "reason": "已入库且内容未变"}
    #计算文件哈希，判断是否需要处理
    #哈希是文件指纹：文件内容没变 → 直接跳过，不重复入库
    old_sha = get_sha(p)
    if old_sha and old_sha != sha:
        try:
            delete_by_source_hash(library, old_sha)
        except Exception:
            pass

    #文件更新场景：删除旧向量
    #同一个路径，上次入库哈希是 old_sha，现在 sha 变了 → 文件被修改→
    #在对应向量库，删除所有 source_hash=old_sha 的分片，
    #清理旧版本；再走新文件入库。

    # 串行入库：embedding 模型 / tokenizer / ChromaDB 是共享资源，
    # 并发调用会触发 Rust 侧「Already borrowed」等异常
    with _INGEST_LOCK:
        try:
            text = extract_text(p)
            if not text or not text.strip():
                mark_skipped(p, sha, library)
                return {"path": str(p), "status": "skipped", "reason": "文档无文本层（可能是扫描版 PDF）"}
            #临界区上锁，串行执行入库核心链路
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

            embs = embed_documents([contextualize(t, m) for t, m in zip(texts, metas)])
            upsert_chunks(library, ids, texts, embs, metas)
            if rebuild:
                rebuild_index(library)
            mark_processed(p, sha, library, len(texts), tags.doc_type, tags.to_metadata())
            return {"path": str(p), "status": "processed", "chunks": len(texts), "doc_type": tags.doc_type}
        except Exception as e:
            mark_error(p, sha, library, str(e))
            return {"path": str(p), "status": "error", "error": str(e)}
       # 异常兜底：任何一步炸了，标记 error 到状态库，返回错误信息，方便上层任务队列重试。
# 上锁区域里面：

# 1. extract_text 抽取文本；抽不出文字（扫描 PDF 图片、空白文件）→ skipped
# 2. `tags = classify(text, filename=p.name, hint_dir=_hint_dir(p, library))`
# LLM 打全套标签：doc_type、年级、篇目、知识点。**这是这套 RAG 很强的一环，不是无脑切块**
# 3. `chunks = chunk_for(tags.doc_type, text)`
# 按文档类型选择切分策略：文言原著切法、教案切法、习题切法分开，不是固定 512token 一刀切
# 4. 遍历分片，生成 chunk id：`f"{sha}-{i}"`，全局唯一；收集 texts、metas
# > 
# > id 设计：文件 hash + 分片序号，文件更新后 hash 变，id 自然换新
# 5. `embs = embed_documents([contextualize(t, m) for t, m in zip(texts, metas)])`
# 👉 这里很关键：不是直接把 chunk.text 拿去 embedding；`contextualize(t,m)` = 给分片追加上下文摘要，比如：
# > 
# > 【文档类型：文言原著，篇目：劝学，年级：高一】 片段：君子曰：学不可以已……
# > 属于**上下文增强的 chunk embedding**，专门解决孤立分片语义丢失，提升召回，是 BGE 系列 RAG 常用技巧。
# 6. `upsert_chunks(library, ids, texts, embs, metas)` 写入向量库（upsert：存在就覆盖，不存在新增）
# 7. rebuild_index (library) 重建索引（可选，参数控制）
# 8. mark_processed：写入 sqlite 状态表，记录成功、分片数量、doc_type
# 9. 返回成功结果字典


#整体数据串联：
# 文件 → process_file()
#     ├─ 哈希校验：无变更跳过
#     ├─ 文件更新：删除旧hash向量
#     ├─ extract_text 抽文本
#     ├─ classify LLM打业务标签（教育元信息）
#     ├─ chunk_for 按文档类型分片
#     ├─ contextualize 给每个分片添上下文摘要
#     ├─ embed_documents → 调用你上一份代码：长短分流、超长滑窗BGE编码
#     └─ upsert_chunks 写入向量库 + sqlite状态记录
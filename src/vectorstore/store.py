from __future__ import annotations

import json

from ..config import CHROMA_DIR

LIBRARY_COLLECTION = {"public": "public_base", "private": "private_kb", "composition": "composition_kb"}
#   3 个 collection：public/private/composition
_client = None  #Chroma PersistentClient 全局单例，只初始化一次
_collections: dict[str, object] = {}

def get_client():
    global _client
    if _client is None:
        import chromadb #延迟导入

        _client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        #创建一个 Chroma 的持久化客户端，并赋值给全局变量 _client。数据存在本地磁盘，重启程序向量库不会丢。
    return _client

def get_collection(library: str):
    if library not in LIBRARY_COLLECTION:
        raise ValueError(f"未知库类型: {library}")#校验传入的逻辑库名称是否合法
    if library not in _collections:
        _collections[library] = get_client().get_or_create_collection(     #存在就读取，不存在新建
            LIBRARY_COLLECTION[library], metadata={"hnsw:space": "cosine"} #向量距离度量方式 = 余弦相似度
        )
    return _collections[library]

def _flatten_meta(meta: dict) -> dict:
    #Chroma 的元数据限制：元数据 value 
    # 只能是 str /int/float /bool，不能直接存 list、dict、None
    out: dict = {}
    for k, v in meta.items():
        if v is None:
            out[k] = ""  #None → 转空字符串
        elif isinstance(v, (list, dict)):
            out[k] = json.dumps(v, ensure_ascii=False) #list /dict → json 序列化字符串
        elif isinstance(v, bool): 
            out[k] = v
        elif isinstance(v, (int, float)):#bool /int/float 原样保留
            out[k] = v
        else:
            out[k] = str(v)#其他类型 → 强制转字符串
    return out

def upsert_chunks(library: str, ids: list[str], texts: list[str],
                  embeddings: list[list[float]], metas: list[dict]) -> None:
    col = get_collection(library)
    flat_metas = [_flatten_meta(m) for m in metas]
    # chroma 单次 upsert 有上限（约 5461），大文件（如资治通鉴近万切片）分批写入
    batch = 5000
    for i in range(0, len(ids), batch):#存在相同 id 就更新，不存在就新增（upsert = update + insert）
        col.upsert(
            ids=ids[i : i + batch],
            documents=texts[i : i + batch],
            embeddings=embeddings[i : i + batch],
            metadatas=flat_metas[i : i + batch],
        )

def delete_by_source_hash(library: str, source_hash: str) -> None:
    #按元数据字段过滤删除
    #source_hash 一般是源文件哈希，同一个文件切出来的所有 chunk 都带这个 hash。
    col = get_collection(library)
    col.delete(where={"source_hash": source_hash})

def get_all_documents(library: str) -> dict:#读取库内全部数据，返回文本 + 元数据，不拿向量
    col = get_collection(library)
    return col.get(include=["documents", "metadatas"])

def count_documents(library: str | None = None) -> dict[str, int]:#指定 library：只查这一个库
    libs = [library] if library else list(LIBRARY_COLLECTION.keys())
    return {lib: get_collection(lib).count() for lib in libs}

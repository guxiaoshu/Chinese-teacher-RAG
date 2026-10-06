from __future__ import annotations

import sys
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st

from src.config import PRIVATE_DIR, PUBLIC_DIR, api_key_ready, CONFIG, BASE_DIR, allowed_doc_types
from src.chunking import chunk_for
from src.ingestion.loader import extract_text
from src.ingestion.state import init_db, list_files, count_by_library
from src.ingestion.watcher import IngestWatcher, scan_existing
from src.vectorstore.store import count_documents
from src.retrieval.retriever import rebuild_index
from src.llm.embeddings import embed_query
from src.pipeline import process_file
from src.chains import lesson_plan, exam, qa, learning_analysis

st.set_page_config(page_title="语文教学 RAG 助手", page_icon="📚", layout="wide")

init_db()

if "watcher" not in st.session_state:
    st.session_state["watcher"] = IngestWatcher(process_file)
    st.session_state["watcher"].start()

@st.cache_resource(show_spinner="正在预热检索索引与向量模型…")
def _warmup() -> bool:
    # 启动时预建 BM25 索引 + 加载向量模型，避免第一条查询卡十几秒
    rebuild_index()
    embed_query("预热")
    return True

_warmup()


def _list_debug_files() -> list[tuple[str, str]]:
    """列出 ingest 下的 txt/md 文件，返回 (显示名, 绝对路径)。"""
    files: list[tuple[str, str]] = []
    for base, lib in ((PUBLIC_DIR, "公共库"), (PRIVATE_DIR, "私有库")):
        for p in sorted(base.rglob("*")):
            if p.is_file() and p.suffix.lower() in (".txt", ".md"):
                files.append((f"{lib} / {p.relative_to(base)}", str(p)))
    return files


def _preview_chunks(text: str, doc_type: str, max_chars: int, overlap: int):
    """用临时参数切分文本（不落库），返回 Chunk 列表。"""
    old_max = CONFIG["chunking"]["max_chunk_chars"]
    old_ov = CONFIG["chunking"]["overlap_chars"]
    CONFIG["chunking"]["max_chunk_chars"] = int(max_chars)
    CONFIG["chunking"]["overlap_chars"] = int(overlap)
    try:
        return chunk_for(doc_type, text)
    finally:
        CONFIG["chunking"]["max_chunk_chars"] = old_max
        CONFIG["chunking"]["overlap_chars"] = old_ov


def _save_chunking_params(max_chars: int, overlap: int) -> None:
    """把切分参数写回 config.yaml（保留注释，定向替换两行）。"""
    CONFIG["chunking"]["max_chunk_chars"] = int(max_chars)
    CONFIG["chunking"]["overlap_chars"] = int(overlap)
    p = BASE_DIR / "config.yaml"
    s = p.read_text(encoding="utf-8")
    s = re.sub(r"max_chunk_chars:\s*\d+", f"max_chunk_chars: {int(max_chars)}", s)
    s = re.sub(r"overlap_chars:\s*\d+", f"overlap_chars: {int(overlap)}", s)
    p.write_text(s, encoding="utf-8")


def _render_citations(citations: list[dict]) -> None:
    if not citations:
        return
    with st.expander(f"📎 引用来源（{len(citations)} 条）"):
        for c in citations:
            lib = "🟢 私有知识库" if c["library"] == "private" else "🔵 公共基准库"
            st.markdown(f"**[{c['index']}]** {lib} · `{c['source_file']}` · {c['doc_type']}")

with st.sidebar:
    st.title("📚 语文教学 RAG 助手")

    if api_key_ready():
        st.success("DeepSeek API 已就绪")
    else:
        st.error("⚠️ 请在 .env 里填入真实 DeepSeek API key（当前是占位符）")

    st.divider()

    doc_counts = count_documents()
    file_counts = count_by_library()
    st.markdown(f"**私有库**：{doc_counts.get('private', 0)} 个切片 / {file_counts.get('private', 0)} 个文件")
    st.markdown(f"**公共库**：{doc_counts.get('public', 0)} 个切片 / {file_counts.get('public', 0)} 个文件")

    st.divider()
    st.subheader("📥 上传入库")
    library = st.radio("入库到", ["私有知识库", "公共基准库"], horizontal=True,
                       help="私有库=你自己的教案/错题/课堂记录；公共库=教材/真题/素材等基准资料")
    lib_key = "private" if library == "私有知识库" else "public"

    uploads = st.file_uploader(
        "拖入 PDF / TXT / DOCX / DOC 文件",
        type=["pdf", "txt", "docx", "doc"],
        accept_multiple_files=True,
        key=f"upload_{lib_key}",
    )
    if uploads:
        dest = PRIVATE_DIR if lib_key == "private" else PUBLIC_DIR
        for u in uploads:
            p = dest / u.name
            p.write_bytes(u.getvalue())
            st.toast(f"已保存 {u.name}，正在入库…")
            try:
                r = process_file(p)
            except Exception as e:
                r = {"path": str(p), "status": "error", "error": str(e)}
            if r.get("status") == "processed":
                st.success(f"✅ {u.name} 入库成功（{r.get('chunks', 0)} 个切片）")
            elif r.get("status") == "skipped":
                st.info(f"⏭️ {u.name}：{r.get('reason', '跳过')}")
            else:
                st.error(f"❌ {u.name}：{r.get('error', r.get('status'))}")

    st.divider()
    col_a, col_b = st.columns(2)
    if col_a.button("🔍 扫描现有文件"):
        with st.spinner("扫描入库中…"):
            processed = scan_existing(process_file)
        st.info(f"扫描完成，处理 {len(processed)} 个文件")
    if col_b.button("🔄 重建索引"):
        with st.spinner("重建中…"):
            rebuild_index()
        st.success("索引已重建")

    st.caption("也可以直接把文件拖进项目里的 `ingest/private` 或 `ingest/public` 文件夹，会自动入库。")

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["✍️ 写教案", "📝 出题", "💬 答疑", "📊 学情分析", "🗂 文件管理", "🔬 切分调试"])

with tab1:
    st.header("针对性备课")
    st.caption("私有库优先召回你往年同篇教案、课堂记录、学生错题 → 公共库补教材课标 → 迭代出新版教案 + 板书 + 课堂预设")
    q = st.text_area("备课需求", placeholder="例如：帮我备《桃花源记》，八年级下，两课时", key="lp")
    if st.button("生成教案", type="primary", key="lp_btn"):
        if not api_key_ready():
            st.error("请先在 .env 填写真实 API key")
        elif q.strip():
            with st.spinner("检索私有库 + 生成教案中（推理模型较慢，请稍候）…"):
                res = lesson_plan.run(q)
            st.markdown(res.content)
            _render_citations(res.citations)

with tab2:
    st.header("针对性出题")
    st.caption("薄弱点必须来自私有错题库；选择题干扰项优先参考学生真实错误作答；对标课标不超纲")
    q = st.text_area("出题需求", placeholder="例如：给《紫藤萝瀑布》出一份 20 分钟随堂练，重点考象征手法", key="exam")
    if st.button("生成试题", type="primary", key="exam_btn"):
        if not api_key_ready():
            st.error("请先在 .env 填写真实 API key")
        elif q.strip():
            with st.spinner("检索私有错题库 + 命题中…"):
                res = exam.run(q)
            st.markdown(res.content)
            _render_citations(res.citations)

with tab3:
    st.header("启发式答疑")
    st.caption("优先召回你课堂用过的例子、批注、学生疑问；启发式引导，不直接给完整答案")
    q = st.text_area("问题", placeholder="例如：学生问《桃花源记》里'乃不知有汉'的'乃'是什么意思，该怎么引导？", key="qa")
    if st.button("开始答疑", type="primary", key="qa_btn"):
        if not api_key_ready():
            st.error("请先在 .env 填写真实 API key")
        elif q.strip():
            with st.spinner("检索老师过往资料 + 生成启发式回复…"):
                res = qa.run(q)
            st.markdown(res.content)
            _render_citations(res.citations)

with tab4:
    st.header("学情沉淀")
    st.caption("基于私有错题/作答样本，输出某篇目/单元的高频错误、易混淆点与教学建议（越沉淀越强）")
    q = st.text_area("学情分析需求", placeholder="例如：分析《桃花源记》这一课学生的整体薄弱点", key="la")
    if st.button("生成学情诊断", type="primary", key="la_btn"):
        if not api_key_ready():
            st.error("请先在 .env 填写真实 API key")
        elif q.strip():
            with st.spinner("分析私有错题中…"):
                res = learning_analysis.run(q)
            st.markdown(res.content)
            _render_citations(res.citations)

with tab5:
    st.header("文件管理")
    rows = list_files()
    if not rows:
        st.info("还没有入库记录。把文件拖进 `ingest/private` 或 `ingest/public` 文件夹，或使用左侧上传。")
    else:
        import pandas as pd

        df = pd.DataFrame(rows)
        cols = ["path", "library", "status", "doc_type", "chunk_count", "processed_at", "error"]
        df = df[[c for c in cols if c in df.columns]]
        df.columns = ["文件路径", "库", "状态", "类型", "切片数", "入库时间", "错误"] if len(df.columns) == 7 else df.columns
        st.dataframe(df, use_container_width=True, height=400)

with tab6:
    st.header("🔬 切分调试")
    st.caption("挑一个文件、调整切分参数，实时预览切片效果；确认后再写回 config.yaml。")

    files = _list_debug_files()
    labels = [f[0] for f in files] + ["✍️ 手动粘贴文本"]
    choice = st.selectbox("选择来源", labels)

    if choice == "✍️ 手动粘贴文本":
        text = st.text_area("粘贴要切分的文本", height=200)
    else:
        path = files[labels.index(choice)][1]
        try:
            text = extract_text(Path(path)) or ""
        except Exception as e:
            text = ""
            st.error(f"读取失败：{e}")
        st.caption(f"来源：{path} · {len(text)} 字符")

    c1, c2, c3 = st.columns([1.3, 1, 1])
    doc_type = c1.selectbox("文档类型（决定切分器）", allowed_doc_types(),
                            index=allowed_doc_types().index("文言原著"))
    max_chars = c2.number_input("max_chunk_chars", 100, 5000, int(CONFIG["chunking"]["max_chunk_chars"]), step=100)
    overlap = c3.number_input("overlap_chars", 0, 500, int(CONFIG["chunking"]["overlap_chars"]), step=20)

    b1, b2 = st.columns(2)
    if b1.button("🔍 预览切分", type="primary", use_container_width=True):
        if not (text or "").strip():
            st.warning("请先选择文件或粘贴文本")
        else:
            chunks = _preview_chunks(text, doc_type, max_chars, overlap)
            if not chunks:
                st.error("切分结果为空")
            else:
                lens = [len(c.text) for c in chunks]
                avg = round(sum(lens) / len(lens))
                short = sum(1 for l in lens if l < 50)
                over = sum(1 for l in lens if l > int(max_chars))
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("切片数", len(chunks))
                m2.metric("平均字数", avg)
                m3.metric("最短 / 最长", f"{min(lens)} / {max(lens)}")
                m4.metric("过短 / 超限", f"{short} / {over}")
                if short:
                    st.info(f"⚠️ 有 {short} 个切片不足 50 字，可能是书名/作者等孤立头没被过滤干净，建议留意。")
                if over:
                    st.info(f"📏 有 {over} 个切片超过 {max_chars} 字（掉进兜底硬切），说明结构切分没兜住这一篇。")
                for i, c in enumerate(chunks):
                    meta = " · ".join(f"{k}={v}" for k, v in c.meta.items())
                    with st.expander(f"#{i+1}  [{len(c.text)}字]  {meta}", expanded=(i < 3)):
                        st.text(c.text[:3000])

    if b2.button("💾 保存参数到 config.yaml", use_container_width=True):
        _save_chunking_params(max_chars, overlap)
        st.success(f"已保存 max_chunk_chars={int(max_chars)} / overlap_chars={int(overlap)}。新入库文件立即生效；已入库切片需重新入库才更新。")

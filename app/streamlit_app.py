from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st

from src.config import PRIVATE_DIR, PUBLIC_DIR, api_key_ready
from src.ingestion.state import init_db, list_files, count_by_library
from src.ingestion.watcher import IngestWatcher, scan_existing
from src.vectorstore.store import count_documents
from src.retrieval.retriever import rebuild_index
from src.pipeline import process_file
from src.chains import lesson_plan, exam, qa, learning_analysis

st.set_page_config(page_title="语文教学 RAG 助手", page_icon="📚", layout="wide")

init_db()

if "watcher" not in st.session_state:
    st.session_state["watcher"] = IngestWatcher(process_file)
    st.session_state["watcher"].start()

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

tab1, tab2, tab3, tab4, tab5 = st.tabs(["✍️ 写教案", "📝 出题", "💬 答疑", "📊 学情分析", "🗂 文件管理"])

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

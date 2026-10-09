from __future__ import annotations

import sys
import re
import hashlib
import base64
import time
from io import BytesIO
from pathlib import Path

from PIL import Image

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st

from src.config import PRIVATE_DIR, PUBLIC_DIR, COMPOSITION_DIR, api_key_ready, CONFIG, BASE_DIR, allowed_doc_types, allowed_grades, PPT_OUTPUT_DIR
from src.chunking import chunk_for
from src.ingestion.loader import extract_text
from src.ingestion.composition import import_reference
from src.ingestion.generated import preview_generated_chunks, save_generated_selected, save_corrected, record_feedback
from src.ingestion.state import init_db, list_files, count_by_library
from src.ingestion.watcher import IngestWatcher, scan_existing
from src.vectorstore.store import count_documents
from src.retrieval.retriever import rebuild_index
from src.llm.embeddings import embed_query
from src.pipeline import process_file
from src.chains import lesson_plan, exam, qa, learning_analysis, essay, ppt, chat
from src.memory import load as load_memory, save as save_memory, SCOPES as MEMORY_SCOPES
from src.history import FEATURES as HISTORY_FEATURES, load as load_history, save as save_history

def _favicon_data_uri() -> str:
    """把北鱼读书图标编码成 data URI 直接当浏览器 favicon。

    用 data URI 而不是传 PIL 图：不经过 Streamlit 的 media 服务，浏览器直接读内嵌数据，
    避免 favicon 不更新/不显示的问题。
    """
    buf = BytesIO()
    Image.open(_ROOT / "images" / "beiyu.png").convert("RGB").save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")

st.set_page_config(page_title="语文教学 RAG 助手", page_icon=_favicon_data_uri(), layout="wide")

init_db()

# —— 会话记录持久化：先把各功能历史从磁盘读回 session_state，之后追加时再写回 ——
for _hk in HISTORY_FEATURES:
    if _hk not in st.session_state:
        st.session_state[_hk] = load_history(_hk)

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
            lib = {"private": "🟢 私有知识库", "composition": "🟠 作文库"}.get(c["library"], "🔵 公共基准库")
            extra = []
            if c.get("authority"):
                extra.append(f"权威：{c['authority']}")
            if c.get("score") is not None:
                extra.append(f"检索分：{c['score']}")
            if c.get("grade"):
                extra.append(f"学段：{c['grade']}")
            if c.get("article"):
                extra.append(f"篇目：{c['article']}")
            suffix = " · " + " · ".join(extra) if extra else ""
            st.markdown(f"**[{c['index']}]** {lib} · `{c['source_file']}` · {c['doc_type']}{suffix}")


def _render_feedback(scenario: str, query: str, content: str, rid: str = "") -> None:
    """👍/👎 反馈 + 编辑后重新入库（修正版成为高权威私有资料）。"""
    nonce = hashlib.sha256((rid or scenario + content).encode("utf-8")).hexdigest()[:10]
    fb1, fb2, fb3 = st.columns([1, 1, 6])
    if fb1.button("👍", key=f"fb_up_{nonce}", help="这个结果不错"):
        record_feedback(query, content, "up")
        st.toast("已记录 👍")
    if fb2.button("👎", key=f"fb_down_{nonce}", help="这个结果需要改进"):
        record_feedback(query, content, "down")
        st.toast("已记录 👎")
    with st.expander("✏️ 编辑后重新入库（改好后作为高权威私有资料，下次优先召回）", expanded=False):
        corrected = st.text_area("修正版", value=content, height=260, key=f"correct_{nonce}", label_visibility="collapsed")
        if st.button("✅ 保存修正版到私有库", key=f"commit_correct_{nonce}"):
            if not (corrected or "").strip():
                st.warning("内容为空，未保存")
            else:
                with st.spinner("正在把修正版作为高权威资料入库…"):
                    ok = save_corrected(scenario, query, corrected)
                if ok:
                    st.success("✅ 已作为高权威资料入库，下次检索会优先命中")
                else:
                    st.error("入库失败")


def _chunk_review(scenario: str, query: str, content: str, rid: str = "", expanded: bool = True) -> None:
    """把本次生成内容切成切片，逐片勾选后手动入库私有库。"""
    info = preview_generated_chunks(scenario, query, content)
    chunks = info["chunks"]
    if not chunks:
        st.caption("（本次内容过短，切不出可入库的切片）")
        return
    nonce = hashlib.sha256((rid or info["sha"]).encode("utf-8")).hexdigest()[:10]
    with st.expander(
        f"📥 手动入库：本次切出 {len(chunks)} 片，勾选要存进私有库的切片（默认全选）",
        expanded=expanded,
    ):
        selected: list[int] = []
        for c in chunks:
            ok = st.checkbox(
                f"切片 {c['index'] + 1}/{len(chunks)} · {len(c['text'])} 字 · {c['text'][:50]}…",
                value=True, key=f"chk_{scenario}_{nonce}_{c['index']}",
            )
            if ok:
                selected.append(c["index"])
        if st.button("✅ 入库所选切片", key=f"commit_{scenario}_{nonce}"):
            if not selected:
                st.warning("没有勾选任何切片，未入库")
            else:
                with st.spinner("正在入库所选切片…"):
                    ok = save_generated_selected(scenario, query, content, selected)
                if ok:
                    st.success(f"✅ 已入库 {len(selected)} 片")
                else:
                    st.error("入库失败")

def _push_round(hist_key: str, scenario: str, q: str, content: str, citations: list, warning: str = "") -> None:
    """把一轮「需求 → 结果」追加进该功能的会话记录，切 tab / 重跑都不丢。"""
    h = st.session_state.setdefault(hist_key, [])
    rid = f"{scenario}-{len(h)}-{int(time.time() * 1000)}"
    h.append({"q": q, "content": content, "citations": citations, "warning": warning, "rid": rid})
    save_history(hist_key, h)


def _render_rounds(hist_key: str, scenario: str) -> None:
    """渲染某功能已保存的多轮记录（切 tab 回来仍可见，同功能多轮累积）。"""
    for r in st.session_state.get(hist_key, []):
        with st.chat_message("user"):
            st.markdown(r["q"])
        with st.chat_message("assistant"):
            st.markdown(r["content"])
            if r.get("warning"):
                st.markdown(r["warning"])
            _render_citations(r.get("citations") or [])
            _chunk_review(scenario, r["q"], r["content"], rid=r["rid"], expanded=False)
            _render_feedback(scenario, r["q"], r["content"], rid=r["rid"])


def _current_memory(feature: str) -> str:
    """右侧「希望我记住什么？」框当前内容；只在该 feature 对应按钮点亮时注入。"""
    scopes = st.session_state.get("memory_scopes")
    if scopes is not None and not scopes.get(feature, True):
        return ""
    return (st.session_state.get("remember_memory_editor") or "").strip()


with st.sidebar:
    st.markdown(
        f"<div style='display:flex;align-items:center;gap:10px'>"
        f"<img src='{_favicon_data_uri()}' width='42' style='border-radius:8px;flex-shrink:0'>"
        f"<span style='font-size:1.6rem;font-weight:700;line-height:1.2'>语文教学 RAG 助手</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

    if api_key_ready():
        st.success("DeepSeek API 已就绪")
    else:
        st.error("⚠️ 请在 .env 里填入真实 DeepSeek API key（当前是占位符）")

    st.divider()

    doc_counts = count_documents()
    file_counts = count_by_library()
    st.markdown(f"**私有库**：{doc_counts.get('private', 0)} 个切片 / {file_counts.get('private', 0)} 个文件")
    st.markdown(f"**公共库**：{doc_counts.get('public', 0)} 个切片 / {file_counts.get('public', 0)} 个文件")
    st.markdown(f"**作文库**：{doc_counts.get('composition', 0)} 篇")

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

main_col, mem_col = st.columns([5, 2], gap="large")

with mem_col:
    st.markdown("#### 🧠 希望我记住什么？")
    st.caption("写在这里的长期上下文会注入「写教案 / 出题 / 答疑 / 学情分析」的生成；作文批改不读取。改完点「保存」即可长期保留。")
    if "memory_scopes" not in st.session_state:
        st.session_state["memory_scopes"] = {s: s in load_memory()["scopes"] for s in MEMORY_SCOPES}
    st.text_area(
        "长期记忆",
        value=load_memory()["text"],
        key="remember_memory_editor",
        height=400,
        label_visibility="collapsed",
        placeholder="例如：我班是八年级，学生文言文基础偏弱；板书偏好思维导图式；喜欢用生活例子导入；讲古文习惯先疏通字词再品情感。",
    )
    st.markdown(
        """
        <style>
        /* 生效范围开关：绿=生效，白=不生效 */
        .st-key-mem_scope_0 button, .st-key-mem_scope_1 button,
        .st-key-mem_scope_2 button, .st-key-mem_scope_3 button {
            border-radius: 0.5rem;
            font-weight: 600;
        }
        .st-key-mem_scope_0 button[data-testid="stBaseButton-primary"],
        .st-key-mem_scope_1 button[data-testid="stBaseButton-primary"],
        .st-key-mem_scope_2 button[data-testid="stBaseButton-primary"],
        .st-key-mem_scope_3 button[data-testid="stBaseButton-primary"] {
            background-color: #28a745 !important;
            border: 1px solid #28a745 !important;
            color: #ffffff !important;
        }
        .st-key-mem_scope_0 button[data-testid="stBaseButton-secondary"],
        .st-key-mem_scope_1 button[data-testid="stBaseButton-secondary"],
        .st-key-mem_scope_2 button[data-testid="stBaseButton-secondary"],
        .st-key-mem_scope_3 button[data-testid="stBaseButton-secondary"] {
            background-color: #ffffff !important;
            border: 1px solid #d0d0d0 !important;
            color: #333333 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.caption("生效范围（绿色 = 生效，白色 = 不生效）：")
    cols = st.columns(2)
    for idx, s in enumerate(MEMORY_SCOPES):
        lit = bool(st.session_state["memory_scopes"].get(s, True))
        if cols[idx % 2].button(
            s, key=f"mem_scope_{idx}", use_container_width=True,
            type="primary" if lit else "secondary",
        ):
            st.session_state["memory_scopes"][s] = not lit
            st.rerun()
    if st.button("💾 保存长期记忆", key="remember_save", use_container_width=True):
        save_memory(
            st.session_state["remember_memory_editor"],
            [s for s in MEMORY_SCOPES if st.session_state["memory_scopes"].get(s)],
        )
        st.toast("✅ 已保存长期记忆")
        st.rerun()

with main_col:
    # —— 临时聊：独立框，可折叠，固定在「写教案」上面 ——
    with st.container(border=True):
        icon_col, title_col, toggle_col = st.columns([0.07, 0.73, 0.20], vertical_alignment="center")
        with icon_col:
            st.image(str(_ROOT / "images" / "deepseek.png"), width=36)
        with title_col:
            st.subheader("临时的聊天，解决一些零碎问题")
        with toggle_col:
            if "chat_open" not in st.session_state:
                st.session_state["chat_open"] = True
            if st.button("收起 ▲" if st.session_state["chat_open"] else "展开 ▼", key="chat_toggle", use_container_width=True):
                st.session_state["chat_open"] = not st.session_state["chat_open"]
                st.rerun()

        if st.session_state["chat_open"]:
            st.caption("不检索知识库、不沉淀入库，直接和 DeepSeek 多轮聊，像网页版一样。刷新页面即清空历史。")

            if "chat_history" not in st.session_state:
                st.session_state["chat_history"] = []

            c1, c2 = st.columns([4, 1])
            with c1:
                use_reason = st.checkbox(
                    "用推理模型（更深，但更慢）", value=False, key="chat_reason",
                    help="勾选走 reason_model（适合需要推理的难题）；不勾用默认快模型。",
                )
            with c2:
                if st.button("🗑 清空对话", key="chat_clear", use_container_width=True):
                    st.session_state["chat_history"] = []
                    st.rerun()

            for m in st.session_state["chat_history"]:
                with st.chat_message(m["role"]):
                    st.markdown(m["content"])

            prompt = st.chat_input("随便问点什么，比如：帮我写一份家长会通知…")
            if prompt:
                if not api_key_ready():
                    st.error("请先在 .env 填写真实 API key")
                else:
                    st.session_state["chat_history"].append({"role": "user", "content": prompt})
                    with st.chat_message("user"):
                        st.markdown(prompt)
                    with st.chat_message("assistant"):
                        try:
                            answer = st.write_stream(chat.stream(st.session_state["chat_history"], use_reason=use_reason))
                        except Exception as e:
                            answer = f"出错了：{e}"
                            st.error(answer)
                    st.session_state["chat_history"].append({"role": "assistant", "content": answer})

    st.divider()

    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs(["✍️ 写教案", "📝 出题", "💬 答疑", "📊 学情分析", "🖊 作文批改", "📽 生成 PPT", "🗂 文件管理", "🔬 切分调试"])

with tab1:
    st.header("针对性备课")
    st.caption("私有库优先召回你往年同篇教案、课堂记录、学生错题 → 公共库补教材课标 → 迭代出新版教案 + 板书 + 课堂预设")
    q = st.text_area("备课需求", placeholder="例如：帮我备《岳阳楼记》，八年级下册，两课时。优先复用我往年上这篇时的提问和板书框架；这届学生文言虚词「其」「以」易错，写进重难点和课堂预设；结尾给 4~6 个跳出课本的启发式问题链（各标思考角度）。", key="lp")
    use_reason = st.checkbox(
        "用推理模型（更深，但更慢）", value=False, key="lp_reason",
        help="勾选走 deepseek-v4-pro（深度优先）；不勾用快模型，速度约快一个量级。",
    )
    if st.button("生成教案", type="primary", key="lp_btn"):
        if not api_key_ready():
            st.error("请先在 .env 填写真实 API key")
        elif q.strip():
            memory = _current_memory("写教案")
            with st.spinner("检索私有库 + 备课中…"):
                user, ctx, citations = lesson_plan.prepare(q, memory)
            ok = True
            with st.chat_message("assistant"):
                try:
                    content = st.write_stream(lesson_plan.stream_from(user, use_reason=use_reason))
                except Exception as e:
                    content = f"出错了：{e}"
                    ok = False
                    st.error(content)
            content = content or ""
            if ok:
                _push_round("hist_lp", "写教案", q, content, citations, lesson_plan.grounding_warning(content, ctx))
                st.session_state["lp"] = ""
                st.rerun()
    _render_rounds("hist_lp", "写教案")

with tab2:
    st.header("针对性出题")
    st.caption("薄弱点必须来自私有错题库；选择题干扰项优先参考学生真实错误作答；对标课标不超纲")
    q = st.text_area("出题需求", placeholder="例如：给《紫藤萝瀑布》出一份 20 分钟随堂练，重点考象征手法与托物言志。选择题干扰项直接用我班学生真实错过的点（借景抒情与象征混淆）；对标课标不超纲，每道题附评分细则。", key="exam")
    if st.button("生成试题", type="primary", key="exam_btn"):
        if not api_key_ready():
            st.error("请先在 .env 填写真实 API key")
        elif q.strip():
            with st.spinner("检索私有错题库 + 命题中…"):
                res = exam.run(q, save=False, memory=_current_memory("出题"))
            _push_round("hist_exam", "出题", q, res.content, res.citations)
            st.session_state["exam"] = ""
            st.rerun()
    _render_rounds("hist_exam", "出题")

with tab3:
    st.header("启发式答疑")
    st.caption("优先召回你课堂用过的例子、批注、学生疑问；启发式引导，不直接给完整答案")
    q = st.text_area("问题", placeholder="例如：学生问《桃花源记》「乃不知有汉」的「乃」怎么理解。我不想直接讲，想用启发式一步步引他自己推出来，借我课堂里讲文言虚词用过的例子和追问方式。", key="qa")
    if st.button("开始答疑", type="primary", key="qa_btn"):
        if not api_key_ready():
            st.error("请先在 .env 填写真实 API key")
        elif q.strip():
            with st.spinner("检索老师过往资料 + 生成启发式回复…"):
                res = qa.run(q, save=False, memory=_current_memory("答疑"))
            _push_round("hist_qa", "答疑", q, res.content, res.citations)
            st.session_state["qa"] = ""
            st.rerun()
    _render_rounds("hist_qa", "答疑")

with tab4:
    st.header("学情沉淀")
    st.caption("基于私有错题/作答样本，输出某篇目/单元的高频错误、易混淆点与教学建议（越沉淀越强）")
    q = st.text_area("学情分析需求", placeholder="例如：分析《桃花源记》这一单元学生的整体薄弱点——高频错误、易混淆点、班级共性，并给针对性教学建议，结论尽量对应我错题库里的具体错题。", key="la")
    if st.button("生成学情诊断", type="primary", key="la_btn"):
        if not api_key_ready():
            st.error("请先在 .env 填写真实 API key")
        elif q.strip():
            with st.spinner("分析私有错题中…"):
                res = learning_analysis.run(q, save=False, memory=_current_memory("学情分析"))
            _push_round("hist_la", "学情分析", q, res.content, res.citations)
            st.session_state["la"] = ""
            st.rerun()
    _render_rounds("hist_la", "学情分析")

with tab5:
    st.header("🖊 作文批改")
    st.caption("高考 60 分制 · ABCDE 五档 · 分项分等（内容/表达/发展），批改后自动沉淀进作文库、按学生追踪写作轨迹")
    c1, c2 = st.columns([3, 1])
    with c1:
        up = st.file_uploader("上传作文文件（txt/docx/pdf/doc，可选）", type=["txt", "docx", "pdf", "doc"], key="essay_up")
        if up is not None:
            tmp = COMPOSITION_DIR / ("_upload_" + up.name)
            tmp.write_bytes(up.getvalue())
            try:
                st.session_state["essay_text"] = extract_text(tmp) or ""
                st.toast(f"已读取 {up.name}")
            except Exception as e:
                st.error(f"读取失败：{e}")
            finally:
                tmp.unlink(missing_ok=True)
        st.text_area("学生作文全文", height=380, key="essay_text",
                     placeholder="把学生作文粘贴到这里…")
    with c2:
        student = st.text_input("学生姓名/学号", key="essay_student", help="用于检索该生过往作文、追踪写作轨迹")
        topic = st.text_input("作文题目/主题", key="essay_topic", placeholder="如：坚持")
        grade = st.selectbox("学段（可选）", [""] + allowed_grades(), key="essay_grade")
        save_essay_flag = st.checkbox("批改后存入作文库", value=True, key="save_essay",
                                      help="勾选=本次作文+评分沉淀进作文库，按学生追踪；不勾=只显示不入库")
        if st.button("开始批改", type="primary", key="essay_btn", use_container_width=True):
            essay_text = st.session_state.get("essay_text", "")
            if not api_key_ready():
                st.error("请先在 .env 填写真实 API key")
            elif not (essay_text or "").strip():
                st.warning("请先粘贴或上传学生作文")
            else:
                with st.spinner("检索过往作文 + 批改评分中…"):
                    res = essay.run(essay_text, student=student, topic=topic, grade=grade, save=save_essay_flag)
                d = res.data or {}
                m1, m2, m3, m4, m5 = st.columns(5)
                m1.metric("总分", f"{d.get('total', '—')}/60")
                m2.metric("档次", d.get("level", "—"))
                m3.metric("内容", f"{d.get('content_score', '—')}/20")
                m4.metric("表达", f"{d.get('expression_score', '—')}/20")
                m5.metric("发展", f"{d.get('development_score', '—')}/20")
                st.markdown(res.content)
                _render_citations(res.citations)
    st.divider()
    st.subheader("📥 导入范文（建评分锚点）")
    st.caption("范文用于给分校准，档次 A~E 由你手动指定；重复导入同文本会自动跳过")
    r1, r2, r3 = st.columns([3, 1.4, 1])
    with r1:
        ref_up = st.file_uploader("上传范文（txt/docx/pdf）", type=["txt", "docx", "pdf"], key="ref_up")
    with r2:
        ref_topic = st.text_input("范文主题", key="ref_topic")
    with r3:
        ref_level = st.selectbox("档次", ["A", "B", "C", "D", "E"], key="ref_level")
    if ref_up is not None and st.button("导入范文", key="ref_btn"):
        tmp = COMPOSITION_DIR / ("_ref_" + ref_up.name)
        tmp.write_bytes(ref_up.getvalue())
        try:
            txt = extract_text(tmp) or ""
            if not txt.strip():
                st.error("范文内容为空")
            elif import_reference(txt, topic=ref_topic, level=ref_level):
                st.success("✅ 已导入范文库")
            else:
                st.info("⏭️ 该范文已存在，跳过")
        except Exception as e:
            st.error(f"导入失败：{e}")
        finally:
            tmp.unlink(missing_ok=True)

with tab6:
    st.header("📽 生成 PPT")
    st.caption("输入主题 → 检索教案资料 → 智能设计引擎生成 .pptx：多风格 / 多版式 / AI 配图 / 自检")

    q = st.text_area("课件主题", placeholder="例如：帮我做《小石潭记》第一课时的课件 PPT，突出「移步换景」的写景顺序和由乐到悲的情感变化，要有原文金句页和两栏对比页。", key="ppt_q")
    use_image = st.checkbox(
        "AI 配图", value=True, key="ppt_image",
        help="用 SiliconFlow 文生图铺底（需在 .env 配 SILICONFLOW_API_KEY）；未配 key 时自动回退纯矢量装饰",
    )
    out_dir = st.text_input(
        "输出文件夹", value=str(PPT_OUTPUT_DIR), key="ppt_outdir",
        help="生成的 .pptx 存这里；可填绝对路径如 D:\\我的PPT，或相对项目路径；文件夹不存在会自动创建",
    )
    if st.button("生成 PPT", type="primary", key="ppt_btn"):
        if not api_key_ready():
            st.error("请先在 .env 填写真实 API key")
        elif not (q or "").strip():
            st.warning("请先填写课件主题")
        else:
            with st.spinner("检索资料 + 生成课件中…"):
                try:
                    res = ppt.run(q, output_dir=out_dir, save=False, use_image=use_image)
                except Exception as e:
                    st.error(f"生成失败：{e}")
                    res = None
            if res:
                d = res.data or {}
                extra = []
                if d.get("style"):
                    extra.append(f"风格：{d['style']}")
                if d.get("used_image"):
                    extra.append("已配 AI 图")
                if d.get("validate"):
                    extra.append(f"自检调整 {d['validate']} 处")
                suffix = f"（{'，'.join(extra)}）" if extra else ""
                st.success(f"✅ 已生成 {d.get('slides', 0)} 页内容 + 封面{suffix}，存于 {d.get('path', '')}")
                st.download_button(
                    "⬇️ 下载 PPT 文件",
                    data=Path(d["path"]).read_bytes(),
                    file_name=d["filename"],
                    mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    key="ppt_dl",
                )
                st.markdown(res.content)
                _render_citations(res.citations)
                _chunk_review("生成PPT", q, res.content)

with tab7:
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

with tab8:
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

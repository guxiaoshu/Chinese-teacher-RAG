from __future__ import annotations

from ..retrieval.retriever import retrieve
from ..llm.deepseek import get_chat_llm, get_reason_llm, invoke_json
from ..config import CONFIG, api_key_ready
from ..ingestion.generated import save_generated
from .common import ChainResult, build_context, with_memory

_SYSTEM = """你是一位资深中学语文教研员，为一位有多年教学沉淀的老师做「针对性备课」。

你会拿到老师自己历年沉淀的资料（【私有知识库】）+ 教材课标（【公共基准库】），
基于这些资料生成**新版教案**，而不是从零编写。

硬性规则：
1. 优先复用老师过去同篇教案的课堂框架、提问、板书、话术，保持其教学风格，只做更新调整。
2. 自动提取往届学生痛点（来自历史错题/作答样本），写进本课「重难点」和「课堂预设」。
3. 课堂探究问题优先选用老师之前验证过有效的问题；没有现成的才新设计，并标注「新设计」。
4. 输出结构：新版教案（课时、教学目标、重难点、教学流程、课堂提问、板书设计）+ 课堂预设（预判学生哪里容易出错，必须注明依据来自历史学生错题）。
5. 在教案末尾新增「💡 启发式问题链」小节：设计 4~6 个**开放式问题**（无唯一标准答案，重在激发思考而非考查记忆）。每个问题标注一个**思考角度**，角度尽量不重复、覆盖多方位，例如：文本细读、情感体验、价值观思辨、跨学科联想、现实关联、比较阅读、批判质疑。这些问题要**跳出课本、调用你广博的知识面**——引入历史背景、哲学、科学、当下生活或其它文学作品，引导学生举一反三、多方位联想，而不是复述课文或检索资料。
6. 所有引用材料用 [n] 标注；引用时说明来自【私有知识库】还是【公共基准库】。
7. 若私有资料之间冲突，以教师手写批注版本为准。
8. 凡是你基于自身知识补充、检索材料里没有的内容，必须标注「（通用知识补充）」，不得伪装成引用材料里的内容。
9. 用 Markdown 输出，语言贴合一线教学，不空谈理论、不套模板话术。
"""

_VERIFY_SYSTEM = """你是教案引用接地校验器。判断一份教案里，哪些结论/说法没有被给定的参考材料支撑（属于模型凭常识补充、但未落到检索材料上的内容）。

规则：
1. 只挑「明显需要材料支撑、但材料里找不到依据」的结论：如具体的学生痛点、课堂细节、某道题的出法、历史背景断言、往年教学事实等。
2. 通用教学常识、礼貌用语、纯方法论不算问题。
3. 只输出 JSON：{"issues": [{"text": "结论原文片段", "reason": "为什么可能未落到材料"}]}；没有则 {"issues": []}。"""


def _verify_grounding(content: str, ctx: str) -> list[dict]:
    if not CONFIG.get("generation", {}).get("verify_grounding", True) or not api_key_ready():
        return []
    try:
        raw = invoke_json([
            {"role": "system", "content": _VERIFY_SYSTEM},
            {"role": "user", "content": f"参考材料：\n{ctx[:8000]}\n\n教案内容：\n{content[:8000]}"},
        ], temperature=0.0)
        return [i for i in (raw.get("issues") or []) if isinstance(i, dict) and (i.get("text") or "").strip()]
    except Exception:
        return []


def _format_warning(issues: list[dict]) -> str:
    """把自检问题格式化成提示块（空列表返回空串）。"""
    if not issues:
        return ""
    lines = [f"\n\n---\n\n⚠️ **引用自检**：以下 {len(issues)} 处结论可能未充分落在检索材料上，建议核对："]
    for i, it in enumerate(issues, 1):
        lines.append(f"\n{i}. {it.get('text', '')}（{it.get('reason', '可能缺少依据')}）")
    return "".join(lines)


def prepare(query: str, memory: str = "") -> tuple[str, str, list[dict]]:
    """检索 + 组装消息，返回 (user 消息, 检索上下文, 引用列表)，供流式与整段生成共用。"""
    docs = retrieve(query)
    ctx, citations = build_context(docs)
    user = with_memory(f"备课需求：{query}\n\n检索到的参考材料：\n{ctx}", memory)
    return user, ctx, citations


def _llm(use_reason: bool, streaming: bool = False):
    return get_reason_llm(streaming=streaming) if use_reason else get_chat_llm(streaming=streaming)


def stream_from(user: str, use_reason: bool = False):
    """流式生成教案正文；检索由 prepare 先取，引用自检由 grounding_warning 后置。"""
    llm = _llm(use_reason, streaming=True)
    for chunk in llm.stream([
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": user},
    ]):
        if chunk.content:
            yield chunk.content


def grounding_warning(content: str, ctx: str) -> str:
    """引用接地自检：标出未落到检索材料上的结论（只提示，不改写，避免二次 pro 开销）。"""
    issues = _verify_grounding(content, ctx)
    return _format_warning(issues)


def run(query: str, save: bool = True, memory: str = "", use_reason: bool = False) -> ChainResult:
    user, ctx, citations = prepare(query, memory)
    llm = _llm(use_reason)
    resp = llm.invoke([
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": user},
    ])
    content = resp.content
    if save:
        save_generated("写教案", query, content)

    # 自检块不并入 content——否则手动入库/修正入库会把警告当教学内容存进私有库，
    # 改由前端单独渲染（data.grounding_warning）。
    return ChainResult(content=content, citations=citations,
                       data={"grounding_warning": grounding_warning(content, ctx)})

from __future__ import annotations

from dataclasses import dataclass, field, asdict

from ..config import allowed_doc_types, allowed_grades, allowed_knowledge_points, allowed_learning_tags
from ..llm.deepseek import invoke_json

_DOC_TYPES = "、".join(allowed_doc_types())
_GRADES = "、".join(allowed_grades())
_KP = "、".join(allowed_knowledge_points())
_LT = "、".join(allowed_learning_tags())

@dataclass
class DocTags:
    grade: str = ""
    unit: str = ""
    article: str = ""
    knowledge_points: list[str] = field(default_factory=list)
    doc_type: str = "其他"
    learning_tags: list[str] = field(default_factory=list)
    situation_note: str = ""
    summary: str = ""

    def to_metadata(self) -> dict:
        return asdict(self)

_SYSTEM = f"""你是一名中学语文教研助理，负责给上传的教学文档打标签，用于后续检索。

文档类型只能是以下之一：{_DOC_TYPES}
学段只能是以下之一：{_GRADES}（无法判断则填空字符串""）
知识点从以下选（可多选，未命中可补充相近词）：{_KP}
学情标签从以下选（可多选）：{_LT}

各文档类型的含义（据此判断，不要轻易归"其他"）：
- 教案：教师备课讲课用的教案、讲义、讲稿、课件、课堂实录、板书设计。
- 课堂笔记：课堂上或教研中记录的笔记、白皮书、教学反思、听课记录。
- 学生错题：学生做错的题目 + 订正 + 教师批注。
- 习题：练习题、试卷、随堂练、作业（题目为主，含答案解析）。
- 学生作答样本：学生完整的作答/作文样例（原文展示学生答案）。
- 文言笔记：文言文的实词/虚词/句式整理、逐篇解析、原文/译文/注释/赏析。文件名含"解析/对译/译文/文言/古文/史记/世说"的多属此类。
- 作文材料：作文主题、范文、立意分析、写作指导。
- 其他：实在无法归入以上类型才用。

文件名关键词提示（结合正文判断，关键词命中时优先采纳）：
- 含"解析版/三行对译/对译/译文/文言/古文/史记/世说新语" → 优先"文言笔记"
- 含"讲义/教案/课件/讲稿" → 优先"教案"（讲义即使含"答案/家长版"字样，只要主体是逐讲授课内容，仍归"教案"）
- 含"白皮书" → 文言文内容归"文言笔记"，诗歌/现代文内容归"课堂笔记"
- 含"错题/订正" → "学生错题"
- 含"作文/立意/范文" → "作文材料"
- 含"试卷/练习/习题/随堂练" → "习题"

请输出一个 JSON 对象，字段如下（都用字符串或字符串数组）：
{{
  "grade": "学段",
  "unit": "单元（无则空串）",
  "article": "篇目/课文名（如 桃花源记、紫藤萝瀑布，无则空串）",
  "knowledge_points": ["知识点1", "知识点2"],
  "doc_type": "文档类型（必须是枚举值）",
  "learning_tags": ["学情标签"],
  "situation_note": "学情具体描述（如：象征含义理解片面；无则空串）",
  "summary": "一句话概括这份文档"
}}

示例 1（课堂笔记）：
输入文件名：紫藤萝瀑布-课堂笔记.txt
输出：{{"grade":"七年级下","unit":"第五单元","article":"紫藤萝瀑布","knowledge_points":["现代文赏析"],"doc_type":"课堂笔记","learning_tags":["学生易踩坑"],"situation_note":"学生对象征含义理解片面，常把托物言志答成借景抒情","summary":"《紫藤萝瀑布》课堂笔记，含象征手法讲解与学生理解误区"}}

示例 2（文言笔记）：
输入文件名：桃花源记-文言实词.docx
输出：{{"grade":"八年级下","unit":"第三单元","article":"桃花源记","knowledge_points":["文言实词"],"doc_type":"文言笔记","learning_tags":[],"situation_note":"","summary":"《桃花源记》文言实词整理，如'悉、咸、皆、乃'等"}}

示例 3（讲义→教案）：
输入文件名：世说新语讲义(30讲）家长版·答案.pdf
输出：{{"grade":"","unit":"","article":"世说新语","knowledge_points":["文言实词","文言虚词"],"doc_type":"教案","learning_tags":[],"situation_note":"","summary":"《世说新语》30 讲讲义，逐讲讲解原文译文与练习"}}

示例 4（解析版→文言笔记）：
输入文件名：古文观止入门篇（解析版）.pdf
输出：{{"grade":"","unit":"","article":"古文观止","knowledge_points":["文言实词","文言虚词","特殊句式"],"doc_type":"文言笔记","learning_tags":[],"situation_note":"","summary":"《古文观止》入门篇逐篇解析，含原文、译文、注释、赏析"}}

示例 5（白皮书→文言笔记）：
输入文件名：北鱼白皮书·文言文版.pdf
输出：{{"grade":"","unit":"","article":"","knowledge_points":["文言实词","文言虚词","特殊句式"],"doc_type":"文言笔记","learning_tags":[],"situation_note":"","summary":"文言文教学教研白皮书，系统梳理文言教学要点"}}

只输出 JSON，不要输出其它内容。"""

def classify(text: str, filename: str = "", hint_dir: str = "") -> DocTags:
    sample = text[:6000]
    if len(text) > 6000:
        sample += "\n...(中段略)...\n" + text[len(text) // 2 : len(text) // 2 + 2000]

    user = f"文件名：{filename}\n目录线索：{hint_dir or '无'}\n\n文档内容：\n{sample}"
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": user},
    ]
    raw = invoke_json(messages, temperature=0.0)

    tags = _sanitize(raw)
    return tags

def _sanitize(raw: dict) -> DocTags:
    doc_type = str(raw.get("doc_type", "其他")).strip()
    if doc_type not in allowed_doc_types():
        doc_type = "其他"

    grade = str(raw.get("grade", "")).strip()
    if grade and grade not in allowed_grades():
        pass

    kp = _as_list(raw.get("knowledge_points"))
    lt = _as_list(raw.get("learning_tags"))
    note = str(raw.get("situation_note", "")).strip()

    return DocTags(
        grade=grade,
        unit=str(raw.get("unit", "")).strip(),
        article=str(raw.get("article", "")).strip(),
        knowledge_points=kp,
        doc_type=doc_type,
        learning_tags=lt,
        situation_note=note,
        summary=str(raw.get("summary", "")).strip(),
    )

def _as_list(v) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        return [v] if v else []
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    return [str(v)]

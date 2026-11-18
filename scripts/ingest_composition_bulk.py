from __future__ import annotations

"""把《作文脑洞》三个 txt（初中篇/三四篇/五六篇）按「一篇一篇」切分入库为作文库范文锚点。

用法：
  1) 试运行（只解析+评级，不删库不入库，产出 JSON 预览）：
       python scripts/ingest_composition_bulk.py --dry-run
  2) 真正执行（删旧作文库 -> 逐篇入库）：
       python scripts/ingest_composition_bulk.py

解析思路：先用「行首编号 + 短行 + 含冒号」的启发式把文件切成“节”，
再交给 DeepSeek 对每一节做【提取范文正文 + 打 A–E 档】，
范文正文要求原样照抄（不改写、不纠 OCR 错字）。
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import COMPOSITION_DIR  # noqa: E402
from src.llm.deepseek import invoke_json  # noqa: E402

SOURCE_DIR = Path(r"C:/Users/BEIYU/Desktop/作文脑洞")
FILES = ["初中篇.txt", "三四篇.txt", "五六篇.txt"]

RUBRIC = """高考作文 60 分制 · 五档评分标准：
【A 档（一等，50–60 分）】切合题意、立意准，中心突出；内容充实，论据扎实；文体规范，结构严谨；语言流畅有质感，字迹工整。发展等级在深刻、丰富、文采、创意中至少一项突出。考场高分范文水平。
【B 档（二等，42–49 分）】符合题意，中心明确；内容比较充实，有论据；文体对，结构完整；语言通顺，少量小语病，字迹清楚。有一点亮点但不够出彩，四平八稳。
【C 档（三等，30–41 分）】基本符合题意，立意沾边但不够精准；中心基本明确，内容单薄，例子老套或论证很浅；文体大体对，结构基本完整；语言基本通顺，语病不算少。
【D 档（四等，18–29 分）】偏离题意，抓不住材料核心；中心模糊，内容空洞；结构松散，语病多；文体混乱；或字数严重不足。
【E 档（17 分及以下）】严重跑题、完全脱离材料；抄袭、套作；字数极少；思想不当；字迹潦草几乎无法辨认。"""

HEAD_PAT = re.compile(r"^([0-9S$]{1,5})[.、。．]\s*(\S.*)$")


def _norm_num(tok: str) -> str:
    return tok.replace("S", "5").replace("$", "5")


def _is_header(s: str) -> bool:
    m = HEAD_PAT.match(s)
    if not m:
        return False
    rest = m.group(2)
    if len(s) > 26:
        return False
    if "?" in rest or "？" in rest:
        return False
    colon = rest.rfind(":")
    if colon == -1:
        # 少数无冒号的节标题（评判细则等）
        return any(k in rest for k in ("评判细则", "审美性评价", "动物的高级写法", "作文鉴赏之法"))
    after = rest[colon + 1 :].strip()
    return 0 < len(after) <= 12


def split_sections(lines: list[str]) -> list[list[str]]:
    """按节切分：节标题单独成行，短且含冒号。文件首行「作文脑洞·xxx」被丢弃。"""
    starts = []
    for i, ln in enumerate(lines, 1):
        if _is_header(ln.strip()):
            starts.append(i - 1)  # 0-based
    out: list[list[str]] = []
    for k in range(len(starts)):
        a = starts[k]
        b = starts[k + 1] if k + 1 < len(starts) else len(lines)
        block = [ln for ln in lines[a:b] if ln.strip() != ""]
        if block:
            out.append(block)
    return out


_SYSTEM = """你是语文教研助手，负责从《作文脑洞》讲义原文中提取「范文」。

讲义每一节通常包含：
- 课前/课后练习题（以【课前…】【课后…】开头，内容是问题、答题横线、序号提示、打分说明等）；
- 真正的范文正文（成篇的学生作文或短文）。

你的任务：
1. 识别并提取每节里所有「范文正文」，剥离一切练习题、题目、答题提示、序号、横线等教学脚手架。
2. 给每篇范文按给定评分标准打一个档次（A/B/C/D/E）。
3. 范文正文必须【原样照抄】原文，不得改写、润色、纠正错别字或标点、补全残缺。只去掉非范文的脚手架内容。

注意：原文存在 OCR 识别产生的错别字、乱码，评分时请忽略这些录入噪声，只按文章本身的题意、立意、内容、结构、文采、创意来判定档次。"""


def _batch_prompt(sections: list[list[str]], offset: int) -> str:
    parts = []
    for j, sec in enumerate(sections):
        idx = offset + j + 1  # 1-based 节序号
        parts.append(f"### 第{idx}节 ###\n" + "\n".join(sec))
    return (
        "评分标准：\n"
        + RUBRIC
        + "\n\n下面是若干节讲义原文（用 ### 第N节 ### 分隔）。"
        + "对每一节，提取该节内所有范文，务必逐节处理、不要遗漏任何一节。只输出一个 JSON 对象，格式：\n"
        + '{"essays": [{"n": 节序号, "title": 范文标题, "level": "A", "body": "范文正文(原样照抄)"}]}\n'
        + "若某节不含成篇范文（纯技法讲解、评判细则等），该节不返回任何元素。不要输出 JSON 以外的文字。\n\n"
        + "\n\n".join(parts)
    )


def extract_and_grade(lines: list[str], limit: int | None = None, workers: int = 8) -> list[dict]:
    from concurrent.futures import ThreadPoolExecutor, as_completed

    sections = split_sections(lines)
    if limit:
        sections = sections[:limit]

    def work(i: int) -> list[dict]:
        prompt = _batch_prompt([sections[i]], i)
        try:
            data = invoke_json(
                [
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,
            )
        except Exception as e:
            print(f"  !! 第{i + 1}节失败: {e}", flush=True)
            return []
        out: list[dict] = []
        for it in (data or {}).get("essays", []):
            if isinstance(it, dict) and (it.get("body") or "").strip():
                it["body"] = it["body"].strip()
                out.append(it)
        return out

    essays: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(work, i) for i in range(len(sections))]
        done = 0
        for fut in as_completed(futs):
            essays.extend(fut.result())
            done += 1
            print(f"  已完成 {done}/{len(sections)} 节，累计范文 {len(essays)} 篇", flush=True)
    return essays


def delete_composition_library() -> None:
    from src.retrieval.retriever import rebuild_index
    from src.vectorstore.store import LIBRARY_COLLECTION, get_client

    n = 0
    for p in COMPOSITION_DIR.glob("*"):
        # 只删逐篇生成的 .md，保留手动放进去的源 .txt（初中篇/三四篇/五六篇）
        if p.is_file() and p.suffix.lower() == ".md":
            p.unlink()
            n += 1
    try:
        get_client().delete_collection(LIBRARY_COLLECTION["composition"])
    except Exception as e:
        print(f"  删除 chroma 集合失败（可能本就不存在）: {e}")
    # 重新拉起空索引（重建 BM25）
    rebuild_index("composition")
    print(f"  已删除作文库 {n} 个文件 + chroma 集合 {LIBRARY_COLLECTION['composition']}")


def ingest(essays: list[dict]) -> tuple[int, int]:
    from src.ingestion.composition import import_reference

    ok = skipped = 0
    for e in essays:
        title = (e.get("title") or "").strip()
        level = (e.get("level") or "").strip().upper()
        if level not in ("A", "B", "C", "D", "E"):
            level = ""
        body = (e.get("body") or "").strip()
        if not body:
            skipped += 1
            continue
        if import_reference(body, topic=title, level=level, title=title):
            ok += 1
        else:
            skipped += 1
    return ok, skipped


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只解析评级，不删库不入库")
    ap.add_argument("--limit", type=int, default=None, help="只处理前 N 节（调试用）")
    ap.add_argument("--workers", type=int, default=8, help="并行 LLM 调用数")
    ap.add_argument("--out", type=str, default=str(ROOT / "data" / "parsed_essays.json"))
    args = ap.parse_args()

    all_essays: list[dict] = []
    for fn in FILES:
        p = SOURCE_DIR / fn
        if not p.exists():
            print(f"跳过缺失文件 {p}")
            continue
        print(f"== 处理 {fn} ==", flush=True)
        lines = p.read_text(encoding="utf-8").splitlines()
        essays = extract_and_grade(lines, limit=args.limit, workers=args.workers)
        for e in essays:
            e["_file"] = fn
        all_essays.extend(essays)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(all_essays, ensure_ascii=False, indent=2), encoding="utf-8")

    # 汇总
    from collections import Counter
    dist = Counter((e.get("level") or "?") for e in all_essays)
    print(f"\n共提取范文 {len(all_essays)} 篇，档次分布：{dict(sorted(dist.items()))}")
    print(f"预览已写入 {args.out}")

    if args.dry_run:
        print("\n=== 前 8 篇预览（标题 | 档 | 正文前 70 字）===")
        for e in all_essays[:8]:
            print(f"- [{e.get('level') or '?'}] {e.get('title','')} | {e['body'][:70]}")
        print("\n试运行完成，未删库、未入库。")
        return

    print("\n开始：删除旧作文库…")
    delete_composition_library()
    print("开始：逐篇入库…")
    ok, skipped = ingest(all_essays)
    print(f"\n完成：成功入库 {ok} 篇，跳过 {skipped} 篇。")


if __name__ == "__main__":
    main()

"""PPT 设计风格库：三套内置风格 + 按课文类型自动匹配。

每套 Style 定义了配色 / 字体 / 底色明暗 / 配图提示词后缀，
deck.py 的版式 builder 全部按 Style 取值渲染。
"""
from __future__ import annotations

from dataclasses import dataclass

from pptx.dml.color import RGBColor


@dataclass(frozen=True)
class Style:
    key: str
    name: str
    bg: RGBColor        # 页面底色
    ink: RGBColor       # 主文字色
    primary: RGBColor   # 主色（山水/强调）
    secondary: RGBColor  # 次色（山水浅）
    accent: RGBColor    # 印章/强调
    gold: RGBColor      # 点缀
    title_font: str
    body_font: str
    light_bg: bool      # 底色是否浅色（决定文字用色）
    image_suffix: str   # 追加到配图提示词的风格后缀


INK = Style(
    key="ink", name="水墨新中式",
    bg=RGBColor(0xF7, 0xF4, 0xEA),
    ink=RGBColor(0x1C, 0x1C, 0x1C),
    primary=RGBColor(0x3B, 0x5F, 0x5B),
    secondary=RGBColor(0x7B, 0xA6, 0x9A),
    accent=RGBColor(0xC0, 0x39, 0x2B),
    gold=RGBColor(0xC9, 0xA8, 0x6A),
    title_font="楷体", body_font="宋体",
    light_bg=True,
    image_suffix="宋代水墨画风格，青绿山水，宣纸纹理，大量留白，清冷幽静，无文字",
)

QINGLV = Style(
    key="qinglv", name="青绿山水",
    bg=RGBColor(0xF1, 0xF6, 0xF3),
    ink=RGBColor(0x1C, 0x1C, 0x1C),
    primary=RGBColor(0x7B, 0xA6, 0x9A),
    secondary=RGBColor(0x3B, 0x5F, 0x5B),
    accent=RGBColor(0xC0, 0x39, 0x2B),
    gold=RGBColor(0xC9, 0xA8, 0x6A),
    title_font="楷体", body_font="宋体",
    light_bg=True,
    image_suffix="青绿山水画风格，石青石绿设色淡雅，留白，清雅宁静，无文字",
)

MINIMAL = Style(
    key="minimal", name="现代极简",
    bg=RGBColor(0xFF, 0xFF, 0xFF),
    ink=RGBColor(0x1C, 0x1C, 0x1C),
    primary=RGBColor(0x2C, 0x5F, 0x5B),
    secondary=RGBColor(0x8A, 0xA6, 0xA0),
    accent=RGBColor(0xC0, 0x39, 0x2B),
    gold=RGBColor(0xC9, 0xA8, 0x6A),
    title_font="微软雅黑", body_font="微软雅黑",
    light_bg=True,
    image_suffix="现代极简插画风格，大色块，大量留白，干净，无文字",
)

STYLES: dict[str, Style] = {s.key: s for s in (INK, QINGLV, MINIMAL)}

# 文言/古诗词类关键词 → 水墨；山水田园类 → 青绿；其余 → 极简
_CLASSICAL = (
    "文言", "古文", "古诗", "诗词", "唐诗", "宋词", "元曲", "诗经", "楚辞", "论语",
    "孟子", "史记", "世说新语", "岳阳楼记", "醉翁亭记", "小石潭记", "桃花源记",
    "出师表", "陋室铭", "爱莲说", "马说", "三峡", "答谢中书书", "记承天寺夜游",
    "湖心亭看雪", "诫子书", "孙权劝学", "卖油翁", "核舟记", "观沧海", "赤壁",
    "诫子", "水调歌头", "岳阳楼", "滕王阁", "木兰诗", "木兰",
)
_LANDSCAPE = ("山水", "田园", "西湖", "春", "秋", "登高", "游", "湖", "江", "溪", "潭", "竹", "雪")


def get(key: str | None) -> Style:
    if key and key in STYLES:
        return STYLES[key]
    return INK


def match_style(query: str, doc_types=()) -> Style:
    """按课文类型自动选风格：文言/古诗→水墨，山水田园→青绿，其余→极简。"""
    s = (query or "") + " " + " ".join(doc_types or [])
    if any(k in s for k in _CLASSICAL):
        return INK
    if any(k in s for k in _LANDSCAPE):
        return QINGLV
    return MINIMAL

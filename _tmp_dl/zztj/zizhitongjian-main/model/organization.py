from typing import List
from pydantic import BaseModel, Field, field_validator


class Organization(BaseModel):
    """组织/官职/群体实体模型。

    Used for organizations, official titles/positions, clans, military units, etc.
    Examples: 丞相府, 太尉, 虎贲军, 智氏家族, 诸侯
    """

    name: str = Field(description="组织/官职/群体名称")

    alias: list[str] = Field(default_factory=list, description="别名/变称")

    original_description_in_book: str = Field(default="", description="原文对该组织的描述")

    description: str = Field(default="", description="补充说明")

    sentence_indexes_in_segment: List[int] = Field(
        default_factory=list,
        description="在文本段落中出现的句子索引列表",
    )

    juan_index: int = Field(default=0, description="The volume index of the book.")

    segment_index: int = Field(default=0, description="The segment index within the volume.")

    @field_validator("original_description_in_book", "description", mode="before")
    @classmethod
    def empty_string_if_none(cls, v):
        if v is None:
            return ""
        return v

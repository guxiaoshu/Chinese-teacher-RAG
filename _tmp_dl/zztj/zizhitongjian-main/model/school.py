from typing import List
from pydantic import BaseModel, Field, field_validator


class School(BaseModel):
    """学派/思想流派实体模型。

    Used for ideological/philosophical schools (e.g. 儒家/法家/道家/墨家/兵家).
    """

    name: str = Field(description="学派/思想流派名称")

    alias: list[str] = Field(default_factory=list, description="别名/变称")

    original_description_in_book: str = Field(default="", description="原文对该学派的描述")

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

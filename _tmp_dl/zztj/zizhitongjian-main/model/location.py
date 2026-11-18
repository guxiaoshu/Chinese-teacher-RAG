from typing import List
from pydantic import BaseModel, Field, field_validator


class Location(BaseModel):
    """
    地理位置模型：表示历史文本中的地理实体
    
    Location model representing geographic entities mentioned in historical texts,
    including cities, states, regions, and landmarks.
    """
    
    name: str = Field(
        description="地点名称，使用最常见的称呼"
    )
    
    alias: List[str] = Field(
        default_factory=list,
        description="地点的所有别名和古今异名"
    )
    
    type: str = Field(
        default="",
        description="地点类型：'国家'、'城市'、'地区'、'山川'、'关隘'等"
    )
    
    description: str = Field(
        default="",
        description="地点的描述，包括地理位置、历史意义等"
    )
    
    modern_name: str = Field(
        default="",
        description="对应的现代地名，便于理解和定位"
    )
    
    coordinates: tuple[float, float] | None = Field(
        default=None,
        description="地理坐标(纬度, 经度)，如果已知"
    )
    
    related_entities: List[str] = Field(
        default_factory=list,
        description="与此地点相关的重要实体名称列表，必须出现在entities列表中"
    )
    
    sentence_indexes_in_segment: List[int] = Field(
        default_factory=list,
        description="地点在文本段落中出现的句子索引列表"
    )

    @field_validator('type', 'description', 'modern_name', mode='before')
    @classmethod
    def empty_string_if_none(cls, v):
        if v is None:
            return ""
        return v


    juan_index: int = Field(
        default=0,
        description="The volume index of the book."
    )

    segment_index: int = Field(
        default=0,
        description="The segment index within the volume."
    )


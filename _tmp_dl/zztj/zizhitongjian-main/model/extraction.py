from typing import List
from pydantic import BaseModel, Field

from .role import Role
from .action import Action
from .event import Event
from .location import Location


class ExtractionResult(BaseModel):
    """
    提取结果模型：从特定文本段提取的结构化数据
    
    Container for structured data extracted from a specific text segment,
    linking entities, relations, events, and locations back to the source text.
    """
    
    segment_index: int = Field(
        description="文本段落索引，用于追溯到原始文本"
    )
    
    segment_start_time: str = Field(
        description="此文本段落的起始时间标记"
    )
    
    source_sentences: List[str] = Field(
        default_factory=list,
        description="原始文本句子列表"
    )
    
    entities: List[Role] = Field(
        default_factory=list,
        description="从此段落提取的所有实体"
    )
    
    relations: List[Action] = Field(
        default_factory=list,
        description="从此段落提取的所有关系"
    )
    
    events: List[Event] = Field(
        default_factory=list,
        description="从此段落识别的历史事件"
    )
    
    locations: List[Location] = Field(
        default_factory=list,
        description="从此段落提取的地理位置"
    )
    
    extraction_metadata: dict = Field(
        default_factory=dict,
        description="提取过程的元数据，如模型版本、时间戳等"
    )


class EntityRelationExtraction(BaseModel):
    """
    实体关系提取响应模型：用于LLM输出的标准格式
    
    Standard response format for LLM entity-relation extraction as defined 
    in the system prompt.
    """
    
    entities: List[Role] = Field(
        description="提取的所有实体列表"
    )
    
    locations: List[Location] = Field(
        default_factory=list,
        description="提取的所有地理位置列表"
    )
    
    events: List[Event] = Field(
        default_factory=list,
        description="提取的所有历史事件列表"
    )
    
    relations: List[Action] = Field(
        description="提取的所有关系列表，其中from/to必须引用entities中的实体"
    )
    
    def validate_relations(self) -> tuple[bool, List[str]]:
        """
        验证所有关系中的实体是否都在entities列表中
        
        Returns:
            (is_valid, error_messages): 验证是否通过及错误信息列表
        """
        entity_names = {entity.name for entity in self.entities}
        for entity in self.entities:
            entity_names.update(entity.alias)
        
        errors = []
        for idx, relation in enumerate(self.relations):
            # Check from_roles
            for from_role in relation.from_roles:
                if from_role not in entity_names:
                    errors.append(
                        f"关系 {idx}: from_roles 中的 '{from_role}' 未在 entities 中定义"
                    )
            
            # Check to_roles
            for to_role in relation.to_roles:
                if to_role not in entity_names:
                    errors.append(
                        f"关系 {idx}: to_roles 中的 '{to_role}' 未在 entities 中定义"
                    )
        
        return (len(errors) == 0, errors)


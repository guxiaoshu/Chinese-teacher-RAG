"""
模型使用示例

Example demonstrating how to use the enhanced models for historical text extraction.
"""

from model import (
    Role, Action, Event, Location, 
    ExtractionResult, EntityRelationExtraction
)


def example_entity_relation_extraction():
    """
    示例：从文本段落中提取实体和关系
    
    模拟LLM返回的结构化数据
    """
    
    # 定义实体
    entities = [
        Role(
            name="智伯",
            alias=["智氏"],
            original_description_in_book="晋阳之战发起方",
            power="智氏家族",
            appear_in_sentence_indexes=[0]
        ),
        Role(
            name="赵襄子",
            alias=["赵襄王"],
            original_description_in_book="",
            power="赵国",
            appear_in_sentence_indexes=[0]
        ),
        Role(
            name="韩",
            alias=["韩国"],
            original_description_in_book="",
            power="韩国",
            appear_in_sentence_indexes=[0]
        ),
        Role(
            name="魏",
            alias=["魏国"],
            original_description_in_book="",
            power="魏国",
            appear_in_sentence_indexes=[0]
        ),
    ]
    
    # 定义关系
    relations = [
        Action(
            time="前453年",
            from_roles=["智伯"],
            to_roles=["赵襄子"],
            action="围攻",
            context="因智氏不满，决定发起围攻",
            result="失败",
            event_name="晋阳之战",
            location="晋阳"
        ),
        Action(
            time="前453年",
            from_roles=["韩", "魏"],
            to_roles=["智伯"],
            action="背叛",
            context="智氏不得人心，韩和魏有所图谋，故联合背叛",
            result="智氏灭亡",
            event_name=None,
            location=None
        ),
    ]
    
    # 创建提取结果
    extraction = EntityRelationExtraction(
        entities=entities,
        relations=relations
    )
    
    # 验证关系的有效性
    is_valid, errors = extraction.validate_relations()
    print(f"验证结果: {'✓ 通过' if is_valid else '✗ 失败'}")
    if errors:
        for error in errors:
            print(f"  - {error}")
    
    return extraction


def example_extraction_result():
    """
    示例：完整的文本段落提取结果
    
    包含实体、关系、事件和地点
    """
    
    # 定义地点
    locations = [
        Location(
            name="晋阳",
            alias=["太原"],
            type="城市",
            description="赵国重要城池，晋阳之战发生地",
            modern_name="山西太原",
            appear_in_segment_indexes=[0]
        )
    ]
    
    # 定义事件
    events = [
        Event(
            name="晋阳之战",
            time="前453年",
            location="晋阳",
            participants=["智伯", "赵襄子", "韩", "魏"],
            description="智伯联合韩魏围攻赵襄子于晋阳，后韩魏倒戈，与赵合灭智氏",
            significance="为三家分晋奠定基础，标志着晋国卿族势力重组",
            related_action_indices=[0, 1],
            source="卷1-段12"
        )
    ]
    
    # 使用之前的提取结果
    extraction = example_entity_relation_extraction()
    
    # 创建完整的提取结果
    result = ExtractionResult(
        segment_index=12,
        segment_start_time="二十年（前376）",
        source_sentences=[
            "前453年，晋阳之战爆发，智伯联合韩、魏围赵襄子于晋阳。",
            "后韩魏倒戈，与赵合灭智氏，三家分晋格局成。"
        ],
        entities=extraction.entities,
        relations=extraction.relations,
        events=events,
        locations=locations,
        extraction_metadata={
            "model": "gpt-4",
            "timestamp": "2026-01-02",
            "version": "1.0"
        }
    )
    
    print("\n" + "="*60)
    print(f"段落 {result.segment_index}: {result.segment_start_time}")
    print("="*60)
    print(f"提取了 {len(result.entities)} 个实体")
    print(f"提取了 {len(result.relations)} 个关系")
    print(f"识别了 {len(result.events)} 个事件")
    print(f"识别了 {len(result.locations)} 个地点")
    
    return result


def example_json_serialization():
    """
    示例：JSON序列化和反序列化
    """
    import json
    
    result = example_extraction_result()
    
    # 序列化为JSON
    json_str = json.dumps(result.model_dump(), indent=2, ensure_ascii=False)
    print("\n" + "="*60)
    print("JSON 序列化结果:")
    print("="*60)
    print(json_str[:500] + "...\n")
    
    # 反序列化
    restored = ExtractionResult.model_validate_json(json_str)
    print(f"✓ 成功反序列化，包含 {len(restored.entities)} 个实体")
    
    return restored


if __name__ == "__main__":
    print("历史文本实体关系提取模型使用示例")
    print("="*60)
    
    # 示例1：基本的实体关系提取
    print("\n【示例 1】实体关系提取与验证")
    example_entity_relation_extraction()
    
    # 示例2：完整的提取结果
    print("\n【示例 2】完整的文本段落提取")
    example_extraction_result()
    
    # 示例3：JSON序列化
    print("\n【示例 3】JSON序列化与反序列化")
    example_json_serialization()
    
    print("\n✓ 所有示例运行完成")


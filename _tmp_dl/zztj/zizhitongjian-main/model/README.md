# 历史文本实体关系提取模型 / Historical Text Entity-Relation Extraction Models

完整的数据模型体系，用于从中文历史文本（如《资治通鉴》）中提取和表示结构化知识。

## 📚 模型概览 / Model Overview

### 核心实体模型 / Core Entity Models

#### 1. `Role` - 实体模型
表示历史人物、组织、国家或文化产物。

**字段 / Fields:**
- `name`: 实体名称
- `alias`: 别名列表
- `original_description_in_book`: 原文描述
- `power`: 所属势力
- `appear_in_sentence_indexes`: 出现位置索引

**示例 / Example:**
```python
from model import Role

entity = Role(
    name="智伯",
    alias=["智氏"],
    original_description_in_book="晋阳之战发起方",
    power="智氏家族",
    appear_in_sentence_indexes=[0]
)
```

#### 2. `Action` - 关系模型
表示实体间的互动关系（军事、政治、社会等）。

**字段 / Fields:**
- `time`: 发生时间
- `from_roles`: 主动方实体名称列表
- `to_roles`: 接收方实体名称列表
- `action`: 具体动作描述
- `context`: 背景信息
- `result`: 结果
- `event_name`: 所属事件名称
- `location`: 发生地点

**示例 / Example:**
```python
from model import Action

relation = Action(
    time="前453年",
    from_roles=["智伯"],
    to_roles=["赵襄子"],
    action="围攻",
    context="因智氏不满，决定发起围攻",
    result="失败",
    event_name="晋阳之战",
    location="晋阳"
)
```

#### 3. `Event` - 事件模型
表示重大历史事件（由多个动作组成）。

**字段 / Fields:**
- `name`: 事件名称
- `time`: 发生时间
- `location`: 发生地点
- `participants`: 参与者列表
- `description`: 详细描述
- `significance`: 历史意义
- `related_action_indices`: 相关动作索引
- `source`: 原文出处

**示例 / Example:**
```python
from model import Event

event = Event(
    name="晋阳之战",
    time="前453年",
    location="晋阳",
    participants=["智伯", "赵襄子", "韩", "魏"],
    description="智伯联合韩魏围攻赵襄子，后韩魏倒戈",
    significance="为三家分晋奠定基础",
    related_action_indices=[0, 1],
    source="卷1-段12"
)
```

#### 4. `Location` - 地理位置模型
表示历史地理实体。

**字段 / Fields:**
- `name`: 地点名称
- `alias`: 别名列表
- `type`: 地点类型（国家/城市/地区等）
- `description`: 描述
- `modern_name`: 现代地名
- `coordinates`: 地理坐标
- `related_entities`: 相关实体
- `appear_in_segment_indexes`: 出现位置

**示例 / Example:**
```python
from model import Location

location = Location(
    name="晋阳",
    alias=["太原"],
    type="城市",
    description="赵国重要城池",
    modern_name="山西太原",
    appear_in_segment_indexes=[0]
)
```

### 提取结果模型 / Extraction Result Models

#### 5. `EntityRelationExtraction` - LLM输出标准格式
用于LLM返回的实体关系提取结果。

**方法 / Methods:**
- `validate_relations()`: 验证关系中的实体是否都存在于entities列表中

**示例 / Example:**
```python
from model import EntityRelationExtraction

extraction = EntityRelationExtraction(
    entities=[entity1, entity2],
    relations=[relation1, relation2]
)

# 验证数据完整性
is_valid, errors = extraction.validate_relations()
if not is_valid:
    for error in errors:
        print(error)
```

#### 6. `ExtractionResult` - 完整提取结果
从特定文本段提取的完整结构化数据。

**字段 / Fields:**
- `segment_index`: 段落索引
- `segment_start_time`: 段落起始时间
- `source_sentences`: 原始句子
- `entities`: 提取的实体
- `relations`: 提取的关系
- `events`: 识别的事件
- `locations`: 识别的地点
- `extraction_metadata`: 提取元数据

### 书籍结构模型 / Book Structure Models

#### 7. `Book`, `Chapter`, `TimeSegment`, `CmpStr`
表示历史文本的层级结构（从 `model.py` 迁移）。

**层级关系 / Hierarchy:**
```
Book (书籍)
├── Chapter (卷)
│   ├── TimeSegment (时间段落)
│   │   ├── CmpStr (对照字符串: 原文+译文)
│   │   └── sentences: List[CmpStr]
```

## 🚀 快速开始 / Quick Start

### 安装依赖
```bash
uv pip install pydantic
```

### 基本使用

```python
from model import (
    Role, Action, Event, Location,
    EntityRelationExtraction, ExtractionResult
)

# 1. 创建实体
entities = [
    Role(name="刘备", alias=["刘玄德"], power="蜀汉"),
    Role(name="曹操", alias=["曹孟德"], power="曹魏"),
]

# 2. 创建关系
relations = [
    Action(
        time="建安五年",
        from_roles=["曹操"],
        to_roles=["刘备"],
        action="进攻",
        context="曹操欲统一北方",
        result="刘备败逃"
    )
]

# 3. 验证数据
extraction = EntityRelationExtraction(
    entities=entities,
    relations=relations
)
is_valid, errors = extraction.validate_relations()

# 4. 创建完整提取结果
result = ExtractionResult(
    segment_index=1,
    segment_start_time="建安五年",
    source_sentences=["曹操进攻刘备..."],
    entities=entities,
    relations=relations,
    events=[],
    locations=[]
)

# 5. 序列化为JSON
import json
json_str = json.dumps(result.model_dump(), indent=2, ensure_ascii=False)
print(json_str)
```

## 📝 完整示例 / Complete Example

运行测试脚本查看完整用法：

```bash
uv run python test_models.py
```

或查看 `model/usage_example.py` 获取更详细的示例。

## 🔗 模型关系图 / Model Relationships

```
┌─────────────────────────────────────────────────────────┐
│                   ExtractionResult                      │
│  (完整的文本段提取结果)                                   │
├─────────────────────────────────────────────────────────┤
│  - segment_index                                        │
│  - segment_start_time                                   │
│  - source_sentences                                     │
│  ├── entities: List[Role]                              │
│  ├── relations: List[Action]                           │
│  ├── events: List[Event]                               │
│  └── locations: List[Location]                         │
└─────────────────────────────────────────────────────────┘
           │                    │
           ▼                    ▼
  ┌─────────────┐      ┌─────────────┐
  │    Role     │◄─────┤   Action    │
  │  (实体)      │      │  (关系)      │
  └─────────────┘      └─────────────┘
           │                    │
           │                    │
           ▼                    ▼
  ┌─────────────┐      ┌─────────────┐
  │  Location   │      │    Event    │
  │  (地点)      │      │  (事件)      │
  └─────────────┘      └─────────────┘
```

## 📋 数据验证 / Data Validation

模型内置了以下验证：

1. **关系完整性验证**: `Action` 中的 `from_roles` 和 `to_roles` 必须引用已存在的实体
2. **类型验证**: Pydantic 自动进行类型检查
3. **必填字段验证**: 确保关键信息不缺失

## 🎯 设计原则 / Design Principles

1. **符合原文**: 严格遵循 `prompts/sys_entity_relation_extraction.md` 中的规范
2. **类型安全**: 使用 Pydantic 进行强类型验证
3. **可扩展性**: 模块化设计，便于添加新的实体类型
4. **可追溯性**: 所有数据都能追溯到原始文本段落
5. **互操作性**: 支持 JSON 序列化/反序列化，便于存储和传输

## 📦 文件结构 / File Structure

```
model/
├── __init__.py              # 导出所有模型
├── role.py                  # 实体模型
├── action.py                # 关系模型
├── event.py                 # 事件模型
├── location.py              # 地点模型
├── extraction.py            # 提取结果模型
├── book_structure.py        # 书籍结构模型
├── usage_example.py         # 详细使用示例
└── README.md               # 本文档
```

## 🔧 与现有系统集成 / Integration

这些模型可以与现有的 LLM 提取流程无缝集成：

```python
# 在提取脚本中
from model import EntityRelationExtraction
import json

def extract_from_segment(segment_text):
    # LLM 提取
    llm_response = llm.complete(prompt + segment_text)
    
    # 解析为模型
    extraction = EntityRelationExtraction.model_validate_json(llm_response)
    
    # 验证数据
    is_valid, errors = extraction.validate_relations()
    if not is_valid:
        # 处理错误...
        pass
    
    return extraction
```

## 📖 参考文档 / References

- 系统提示: `prompts/sys_entity_relation_extraction.md`
- 原始模型: `model.py`
- 测试脚本: `test_models.py`

---

**版本**: 1.0  
**更新日期**: 2026-01-02  
**维护者**: 资治通鉴知识图谱项目组


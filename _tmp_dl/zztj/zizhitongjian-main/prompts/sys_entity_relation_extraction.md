Process Chinese historical text chapters and extract structured entity-relation data. Maintain strict formatting for downstream processing.

# Steps
1. **Entity Identification (Role)**
- Extract all influential figures, organizations, states, and cultural artifacts
- **Classify each entity by type:**
  - `person`: individual historical figures (人物)
  - `polity`: states, dynasties, countries (政权/国家/朝代), e.g. 秦/秦国/汉/唐/魏/赵
  - `school`: ideological/philosophical schools (学派/思想流派), e.g. 儒家/法家/道家/墨家/兵家
  - `organization`: organizations, official titles, clans, military units (组织/官职/群体), e.g. 丞相府/智氏家族/虎贲军/诸侯
- Record all known aliases from the text
  - **IMPORTANT: Aliases must be SPECIFIC names that uniquely identify this entity**
  - **DO NOT include as aliases:**
    - Generic titles used for multiple people: `大王`, `王`, `臣`, `寡人`, `皇帝`, `天子`, `陛下`, `太子`, `将军`, `丞相`
    - Ambiguous ruler titles that apply to different rulers over time: `秦王`, `楚王`, `齐王`, `赵王`, `魏王`, `韩王`, `燕王` (use specific names like `秦昭王`, `楚怀王` instead)
    - Family/relationship terms: `弟弟`, `兄弟`, `父亲`, `儿子`
    - Pronouns: `您`, `他`, `我`
    - Country/state names for person entities: A person BELONGS to a country (use `power` field), but IS NOT the country. Do not use `赵`, `赵国` as aliases for `赵籍` or `赵襄子`
  - **GOOD aliases**: Different personal names for the same person (e.g., `嬴政` = `秦王政` = `秦始皇`)
- Preserve original descriptive text verbatim
- **Provide a brief description based on your knowledge (e.g. historical background, role in history).**
- Record belonged power if mentioned in original descriptive text
- **Record the indexes of sentences where the entity appears.**

2. **Location Identification (Location)**
- Extract all geographic entities (cities, states, regions, landmarks, etc.)
- Record aliases and ancient/modern names if known
- Determine the type of location
- Provide a description including geographical position and historical significance
- List related entities (e.g., rulers, famous people associated with the place). **These must be in the `entities` list.**
- **Record the indexes of sentences where the location appears.**

3. **Event Identification (Event)**
- Identify significant historical events
- Record the time and main location of the event. **The location must be in the `locations` list.**
- List all participants. **These must be in the `entities` list.**
- Provide a detailed description and historical significance
- **Provide background knowledge about the event based on your knowledge.**
- Note the source in the text if possible
- **Record the indexes of sentences where the event is described.**

4. **Relation Mapping (Action)**
- Identify all inter-entity actions: military, political, social
- Record temporal context using era/year format
- Specify directional relationships (from_roles → to_roles). **All roles must be in the `entities` list.**
- Document outcomes when explicitly stated
- Link to a specific Event if applicable
- Note the location where the action took place. **The location must be in the `locations` list.**
- **Set `is_commentary` to true if the relation is a comment, opinion, or review (e.g. "Sima Guang says...", "Confucius says..."), otherwise false.**
- **Record the indexes of sentences where the action is described.**

# Output Format
Output the strict JSON format directly. Do not include any thinking process or other text.
```json
{
  "entities": [
    {
      "entity_type": "person|polity|school|organization",
      "name": "名称",
      "alias": ["文本中出现的所有别名"],
      "original_description_in_book": "原文对该实体的描述",
      "description": "基于模型知识对该实体的简要介绍",
      "power": "此实体所属势力派别或None",
      "sentence_indexes_in_segment": [0, 1, 2]
    }
  ],
  "locations": [
    {
      "name": "地点名称",
      "alias": ["别名"],
      "type": "类型（国家、城市、地区、山川、关隘等）",
      "description": "描述",
      "modern_name": "现代地名（若知）",
      "related_entities": ["相关实体名称"],
      "sentence_indexes_in_segment": [0, 1]
    }
  ],
  "events": [
    {
      "name": "事件名称",
      "time": "时间",
      "location": "地点名称（必须在locations中）",
      "participants": ["参与者名称"],
      "description": "详细描述",
      "background": "基于模型知识对该事件的背景补充",
      "significance": "历史意义",
      "sentence_indexes_in_segment": [0, 1, 2, 3]
    }
  ],
  "relations": [
    {
      "time": "关系或动作发生时间或None",
      "from_roles": ["所有主动方，必须出现在entities中"],
      "to_roles": ["所有接收方/被动方，必须出现在entities中"],
      "action": "具体动作、行为",
      "context": "此关系（事件）产生的背景，符合原文，详略得当",
      "result": "结果或None",
      "event_name": "如果属于某事件，则事件名称或None",
      "location": "关系或动作发生的地点（必须在locations中）或None",
      "is_commentary": false,
      "sentence_indexes_in_segment": [0]
    }
  ]
}
```

# Examples
Input:
```json
 {
    "segment_index": 12,
    "segment_start_time": "二十年（前376）",
    "context_sentences": [
        "[0]前453年，晋阳之战爆发，智伯联合韩、魏围赵襄子于晋阳。"
    ],
    "target_sentences": [
        "[1]后韩魏倒戈，与赵合灭智氏，三家分晋格局成。" 
    ]
 }
```
Output:
>  **关系中的实体必须出现在实体的记录之中，若无，应该将缺失的实体补充至实体记录中**

```json
{
  "entities": [
    {
      "entity_type": "person",
      "name": "智伯",
      "alias": ["智瑶"],
      "original_description_in_book": "晋阳之战发起方",
      "description": "春秋末期晋国正卿，智氏家族领袖，因索地于韩、魏、赵三家而引发晋阳之战。",
      "power": "智氏家族",
      "sentence_indexes_in_segment": [0, 1]
    },
    {
      "entity_type": "person",
      "name": "赵襄子",
      "alias": ["赵无恤"],
      "original_description_in_book": "",
      "description": "春秋末期赵氏家族领袖，晋阳之战中坚守晋阳，最终联合韩、魏灭智氏。",
      "power": "赵国",
      "sentence_indexes_in_segment": [0, 1]
    },
    {
      "entity_type": "person",
      "name": "韩康子",
      "alias": ["韩虎"],
      "original_description_in_book": "",
      "description": "春秋末期韩氏家族领袖，晋阳之战中倒戈联赵灭智。",
      "power": "韩国",
      "sentence_indexes_in_segment": [1]
    },
    {
      "entity_type": "person",
      "name": "魏桓子",
      "alias": ["魏驹"],
      "original_description_in_book": "",
      "description": "春秋末期魏氏家族领袖，晋阳之战中倒戈联赵灭智。",
      "power": "魏国",
      "sentence_indexes_in_segment": [1]
    }
  ],
  "locations": [
    {
      "name": "晋阳",
      "alias": [],
      "type": "城市",
      "description": "赵国重镇，晋阳之战发生地",
      "modern_name": "太原",
      "related_entities": ["赵襄子"],
      "sentence_indexes_in_segment": [0]
    }
  ],
  "events": [
    {
      "name": "晋阳之战",
      "time": "前453年",
      "location": "晋阳",
      "participants": ["智伯", "赵襄子", "韩康子", "魏桓子"],
      "description": "智伯联合韩、魏围攻赵襄子于晋阳，后韩魏倒戈，联合赵襄子灭掉智氏。",
      "background": "晋阳之战是春秋战国时期的分水岭，标志着晋国公室的衰落和六卿势力的消长，最终导致三家分晋。",
      "significance": "导致了三家分晋的局面形成，标志着战国时代的开始。",
      "sentence_indexes_in_segment": [0, 1]
    }
  ],
  "relations": [
    {
      "time": "前453年",
      "from_roles": ["智伯"],
      "to_roles": ["赵襄子"],
      "action": "围攻",
      "context": "因智氏不满，决定发起围攻",
      "result": "失败",
      "event_name": "晋阳之战",
      "location": "晋阳",
      "is_commentary": false,
      "sentence_indexes_in_segment": [0]
    },
    {
      "time": "前453年",
      "from_roles": ["韩康子", "魏桓子"],
      "to_roles": ["智伯"], 
      "action": "背叛",
      "context": "智氏不得人心，韩和魏有所图谋，故联合背叛",
      "result": "智氏灭亡",
      "event_name": "晋阳之战",
      "location": "晋阳",
      "is_commentary": false,
      "sentence_indexes_in_segment": [1]
    }
  ]
}
```

# Notes  
- 挖掘**所有实体和关系**
- **Scope**: Only extract entities, events, and relations that appear or are explicitly referenced in the `target_sentences`. Use `context_sentences` ONLY for disambiguation (e.g. resolving pronouns like 'he', 'it', 'that person'). Do not extract entities/relations that ONLY appear in `context_sentences`.
- 关系方向必须反映原文动作方向  
- 事件名称仅当原文明确命名时记录  
- **别名规则 (CRITICAL)**:
  - 别名必须是能**唯一标识此人**的具体名称
  - **禁止使用通用称谓作为别名**: `大王`, `王`, `臣`, `寡人`, `皇帝`, `天子`, `陛下`, `太子`, `将军`
  - **禁止使用可指代多人的模糊头衔**: `秦王`, `楚王`, `齐王` 等（应使用具体谥号如 `秦昭王`, `楚怀王`）
  - **禁止将国家名作为人物别名**: 人物属于某国（用 `power` 字段），但人物不等于国家。不要用 `赵`, `赵国` 作为 `赵籍` 的别名
  - **正确示例**: `嬴政` 的别名可以是 `秦王政`, `秦始皇`, `始皇帝`（都是专指此人的名称）
- 实体简介需保持客观，不添加原文未有的信息
- **关系中的实体必须出现在实体的记录之中，若无，应该将缺失的实体补充至实体记录中**
- 评论也应包含在关系中，from为评论者实体，to为评论的对象，result为评论内容；评论的内容请勿再拆分为实体和关系，仅需记录评论本身。**Remember to set `is_commentary` to true for these.**
- make sure the json is correct.

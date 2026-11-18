"""
历史文本实体关系提取模型

Models for extracting entities and relations from historical Chinese texts.
"""

from .role import Role
from .action import Action
from .event import Event
from .location import Location
from .extraction import ExtractionResult, EntityRelationExtraction
from .book_structure import CmpStr, TimeSegment, Chapter, Book
from .unified import (
    UnifiedRole,
    UnifiedLocation,
    UnifiedEvent,
    UnifiedRelation,
    UnifiedKnowledgeBase,
    EntityOccurrence,
)

__all__ = [
    # Raw extraction models
    "Role",
    "Action",
    "Event",
    "Location",
    "ExtractionResult",
    "EntityRelationExtraction",
    "CmpStr",
    "TimeSegment",
    "Chapter",
    "Book",
    # Unified/resolved models
    "UnifiedRole",
    "UnifiedLocation",
    "UnifiedEvent",
    "UnifiedRelation",
    "UnifiedKnowledgeBase",
    "EntityOccurrence",
]


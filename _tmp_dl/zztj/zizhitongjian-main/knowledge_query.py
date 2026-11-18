"""
Knowledge Query: Search and retrieval interface for unified knowledge base.

Provides efficient querying capabilities for visualization and search:
- Entity lookup by name/alias
- Relationship traversal
- Time-based filtering
- Power/faction grouping
"""

import json
import re
from typing import List, Dict, Optional, Set, Tuple
from pathlib import Path
from dataclasses import dataclass

from model.unified import (
    UnifiedRole, UnifiedLocation, UnifiedEvent, UnifiedRelation,
    UnifiedKnowledgeBase
)


@dataclass
class SearchResult:
    """A search result with relevance score."""
    entity_type: str  # 'role', 'location', 'event', 'relation'
    entity_id: str
    name: str
    description: str
    score: float
    matched_field: str


class KnowledgeQuery:
    """
    Query interface for the unified knowledge base.
    
    Provides methods for:
    - Looking up entities by name or alias
    - Finding related entities
    - Filtering by time period, power, juan
    - Full-text search across descriptions
    """
    
    def __init__(self, kb: UnifiedKnowledgeBase):
        self.kb = kb
        self._build_search_index()
    
    def _build_search_index(self) -> None:
        """Build inverted index for full-text search."""
        self.search_index: Dict[str, List[Tuple[str, str, str]]] = {}
        
        # Index roles
        for role_id, role in self.kb.roles.items():
            self._index_text(role.canonical_name, 'role', role_id, 'name')
            for name in role.all_names:
                self._index_text(name, 'role', role_id, 'alias')
            self._index_text(role.description, 'role', role_id, 'description')
        
        # Index locations
        for loc_id, loc in self.kb.locations.items():
            self._index_text(loc.canonical_name, 'location', loc_id, 'name')
            for name in loc.all_names:
                self._index_text(name, 'location', loc_id, 'alias')
            self._index_text(loc.description, 'location', loc_id, 'description')
        
        # Index events
        for event_id, event in self.kb.events.items():
            self._index_text(event.name, 'event', event_id, 'name')
            self._index_text(event.description, 'event', event_id, 'description')
    
    def _index_text(self, text: str, entity_type: str, entity_id: str, field: str) -> None:
        """Add text to search index."""
        if not text:
            return
        # Simple character-level indexing for Chinese text
        for char in text:
            if char.strip():
                if char not in self.search_index:
                    self.search_index[char] = []
                self.search_index[char].append((entity_type, entity_id, field))
    
    # ============ Entity Lookup ============
    
    def get_role(self, name: str) -> Optional[UnifiedRole]:
        """Get role by name or alias."""
        role_id = self.kb.name_to_role_id.get(name)
        if role_id:
            return self.kb.roles.get(role_id)
        return None
    
    def get_location(self, name: str) -> Optional[UnifiedLocation]:
        """Get location by name or alias."""
        loc_id = self.kb.name_to_location_id.get(name)
        if loc_id:
            return self.kb.locations.get(loc_id)
        return None
    
    def get_event(self, name: str) -> Optional[UnifiedEvent]:
        """Get event by name."""
        return self.kb.events.get(name)
    
    def resolve_name(self, name: str) -> Optional[str]:
        """
        Resolve any name/alias to its canonical ID.
        
        Returns canonical role ID, or None if not found.
        """
        return self.kb.name_to_role_id.get(name)
    
    # ============ Relationship Queries ============
    
    def get_relations_for(self, entity_name: str) -> List[UnifiedRelation]:
        """Get all relations involving an entity (as source or target)."""
        canonical_id = self.resolve_name(entity_name) or entity_name
        
        results = []
        for rel in self.kb.relations.values():
            if rel.from_entity == canonical_id or rel.to_entity == canonical_id:
                results.append(rel)
        return results
    
    def get_outgoing_relations(self, entity_name: str) -> List[UnifiedRelation]:
        """Get relations where entity is the source."""
        canonical_id = self.resolve_name(entity_name) or entity_name
        return [r for r in self.kb.relations.values() if r.from_entity == canonical_id]
    
    def get_incoming_relations(self, entity_name: str) -> List[UnifiedRelation]:
        """Get relations where entity is the target."""
        canonical_id = self.resolve_name(entity_name) or entity_name
        return [r for r in self.kb.relations.values() if r.to_entity == canonical_id]
    
    def get_related_entities(self, entity_name: str) -> Set[str]:
        """Get all entities directly related to the given entity."""
        role = self.get_role(entity_name)
        if role:
            return role.related_entities
        return set()
    
    def find_connection(self, entity1: str, entity2: str, max_hops: int = 3) -> List[List[str]]:
        """
        Find connection paths between two entities.
        
        Returns list of paths, where each path is a list of entity names.
        """
        id1 = self.resolve_name(entity1) or entity1
        id2 = self.resolve_name(entity2) or entity2
        
        if id1 == id2:
            return [[id1]]
        
        # BFS for shortest paths
        from collections import deque
        
        queue = deque([(id1, [id1])])
        visited = {id1}
        paths = []
        
        while queue:
            current, path = queue.popleft()
            
            if len(path) > max_hops + 1:
                continue
            
            # Get neighbors
            neighbors = set()
            for rel in self.kb.relations.values():
                if rel.from_entity == current:
                    neighbors.add(rel.to_entity)
                if rel.to_entity == current:
                    neighbors.add(rel.from_entity)
            
            for neighbor in neighbors:
                if neighbor == id2:
                    paths.append(path + [neighbor])
                elif neighbor not in visited and len(path) < max_hops:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))
        
        return paths
    
    # ============ Filtering ============
    
    def get_roles_by_power(self, power: str) -> List[UnifiedRole]:
        """Get all roles belonging to a power/faction."""
        role_ids = self.kb.power_to_roles.get(power, [])
        return [self.kb.roles[rid] for rid in role_ids if rid in self.kb.roles]
    
    def get_roles_in_juan(self, juan_index: int) -> List[UnifiedRole]:
        """Get all roles that appear in a specific 卷."""
        role_ids = self.kb.juan_to_roles.get(juan_index, [])
        return [self.kb.roles[rid] for rid in role_ids if rid in self.kb.roles]
    
    def get_events_in_juan(self, juan_index: int) -> List[UnifiedEvent]:
        """Get all events in a specific 卷."""
        event_ids = self.kb.juan_to_events.get(juan_index, [])
        return [self.kb.events[eid] for eid in event_ids if eid in self.kb.events]
    
    def get_roles_by_time(self, start_year: int, end_year: int) -> List[UnifiedRole]:
        """
        Get roles active during a time period.
        
        Years should be negative for BC (e.g., -403 for 前403年).
        """
        # This requires roles to have time information populated
        # For now, filter by juans that roughly correspond to time periods
        results = []
        for role in self.kb.roles.values():
            # If we have activity period, use it
            if role.active_period:
                # Parse and compare
                pass
            # Otherwise include if appears in early juans for early BC dates
            results.append(role)
        return results
    
    def get_all_powers(self) -> List[str]:
        """Get list of all powers/factions."""
        return list(self.kb.power_to_roles.keys())
    
    def get_power_distribution(self) -> Dict[str, int]:
        """Get count of roles per power."""
        return {power: len(roles) for power, roles in self.kb.power_to_roles.items()}
    
    # ============ Search ============
    
    def search(self, query: str, limit: int = 20) -> List[SearchResult]:
        """
        Full-text search across all entities.
        
        Returns results sorted by relevance score.
        """
        results: Dict[Tuple[str, str], SearchResult] = {}
        
        # Score each matching entity
        for char in query:
            if char in self.search_index:
                for entity_type, entity_id, field in self.search_index[char]:
                    key = (entity_type, entity_id)
                    if key not in results:
                        # Get entity details
                        name, desc = self._get_entity_info(entity_type, entity_id)
                        results[key] = SearchResult(
                            entity_type=entity_type,
                            entity_id=entity_id,
                            name=name,
                            description=desc,
                            score=0,
                            matched_field=field
                        )
                    
                    # Boost score based on field importance
                    boost = 3.0 if field == 'name' else (2.0 if field == 'alias' else 1.0)
                    results[key].score += boost
        
        # Sort by score and return top results
        sorted_results = sorted(results.values(), key=lambda r: -r.score)
        return sorted_results[:limit]
    
    def _get_entity_info(self, entity_type: str, entity_id: str) -> Tuple[str, str]:
        """Get name and description for an entity."""
        if entity_type == 'role':
            role = self.kb.roles.get(entity_id)
            if role:
                return role.canonical_name, role.description
        elif entity_type == 'location':
            loc = self.kb.locations.get(entity_id)
            if loc:
                return loc.canonical_name, loc.description
        elif entity_type == 'event':
            event = self.kb.events.get(entity_id)
            if event:
                return event.name, event.description
        return entity_id, ""
    
    def search_roles(self, query: str, limit: int = 20) -> List[UnifiedRole]:
        """Search only roles."""
        results = self.search(query, limit * 2)
        roles = []
        for r in results:
            if r.entity_type == 'role' and r.entity_id in self.kb.roles:
                roles.append(self.kb.roles[r.entity_id])
                if len(roles) >= limit:
                    break
        return roles
    
    # ============ Statistics ============
    
    def get_top_roles(self, n: int = 10) -> List[UnifiedRole]:
        """Get roles with most mentions."""
        sorted_roles = sorted(
            self.kb.roles.values(),
            key=lambda r: r.total_mentions,
            reverse=True
        )
        return sorted_roles[:n]
    
    def get_most_connected_roles(self, n: int = 10) -> List[Tuple[UnifiedRole, int]]:
        """Get roles with most relationships."""
        role_connection_count = {}
        for rel in self.kb.relations.values():
            role_connection_count[rel.from_entity] = role_connection_count.get(rel.from_entity, 0) + 1
            role_connection_count[rel.to_entity] = role_connection_count.get(rel.to_entity, 0) + 1
        
        sorted_roles = sorted(role_connection_count.items(), key=lambda x: -x[1])[:n]
        return [
            (self.kb.roles[rid], count)
            for rid, count in sorted_roles
            if rid in self.kb.roles
        ]
    
    def get_summary(self) -> Dict:
        """Get summary statistics of the knowledge base."""
        return {
            "total_roles": self.kb.total_roles,
            "total_locations": self.kb.total_locations,
            "total_events": self.kb.total_events,
            "total_relations": self.kb.total_relations,
            "total_powers": len(self.kb.power_to_roles),
            "juans_processed": len(self.kb.juans_processed),
            "top_powers": sorted(
                self.kb.power_to_roles.items(),
                key=lambda x: -len(x[1])
            )[:10]
        }


def load_knowledge_base(path: str) -> KnowledgeQuery:
    """Load unified knowledge base and create query interface."""
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    kb = UnifiedKnowledgeBase(**data)
    return KnowledgeQuery(kb)


if __name__ == "__main__":
    # Demo usage
    import argparse
    
    parser = argparse.ArgumentParser(description="Query the unified knowledge base")
    parser.add_argument("--kb-path", default="data/unified_knowledge.json", help="Knowledge base file")
    parser.add_argument("--search", type=str, help="Search query")
    parser.add_argument("--role", type=str, help="Look up a role by name")
    parser.add_argument("--relations", type=str, help="Get relations for an entity")
    parser.add_argument("--summary", action="store_true", help="Show summary statistics")
    
    args = parser.parse_args()
    
    query = load_knowledge_base(args.kb_path)
    
    if args.summary:
        print(json.dumps(query.get_summary(), ensure_ascii=False, indent=2))
    
    if args.search:
        results = query.search(args.search)
        print(f"\nSearch results for '{args.search}':")
        for r in results[:10]:
            print(f"  [{r.entity_type}] {r.name} (score: {r.score:.1f})")
            if r.description:
                print(f"    {r.description[:100]}...")
    
    if args.role:
        role = query.get_role(args.role)
        if role:
            print(f"\nRole: {role.canonical_name}")
            print(f"  Aliases: {', '.join(role.all_names)}")
            print(f"  Power: {role.primary_power}")
            print(f"  Mentions: {role.total_mentions}")
            print(f"  Juan span: {role.first_appearance_juan} - {role.last_appearance_juan}")
            print(f"  Description: {role.description}")
        else:
            print(f"Role '{args.role}' not found")
    
    if args.relations:
        relations = query.get_relations_for(args.relations)
        print(f"\nRelations for '{args.relations}':")
        for rel in relations[:20]:
            print(f"  {rel.from_entity} --[{rel.primary_action}]--> {rel.to_entity} (x{rel.interaction_count})")

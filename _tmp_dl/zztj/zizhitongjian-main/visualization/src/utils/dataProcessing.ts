import type {
  JuanData,
  Extraction,
  Role,
  Location,
  Event,
  Action,
  RoleNode,
  RoleLink,
  TimelineEvent,
  PowerDistribution,
} from '../types';

// Parse ancient Chinese year format to numeric value
export function parseChineseYear(timeStr: string | null): number | null {
  if (!timeStr) return null;
  
  // Match patterns like "前403年", "前453", "威烈王二十三年（前403）"
  const bcMatch = timeStr.match(/前(\d+)/);
  if (bcMatch) {
    return -parseInt(bcMatch[1], 10);
  }
  
  // Match patterns like "公元前403年"
  const fullBcMatch = timeStr.match(/公元前(\d+)/);
  if (fullBcMatch) {
    return -parseInt(fullBcMatch[1], 10);
  }
  
  return null;
}

// Aggregate roles from all extractions
export function aggregateRoles(data: JuanData): Map<string, RoleNode> {
  const roleMap = new Map<string, RoleNode>();
  
  Object.values(data).forEach((extraction: Extraction) => {
    extraction.entities.forEach((entity: Role) => {
      const existing = roleMap.get(entity.name);
      if (existing) {
        existing.appearances += 1;
        if (!existing.juans.includes(entity.juan_index)) {
          existing.juans.push(entity.juan_index);
        }
        // Add new aliases
        entity.alias.forEach((alias) => {
          if (!existing.aliases.includes(alias)) {
            existing.aliases.push(alias);
          }
        });
        // Add new description if different and non-empty
        if (entity.description && !existing.descriptions.includes(entity.description)) {
          existing.descriptions.push(entity.description);
        }
        // Update main description if the new one is longer
        if (entity.description.length > existing.description.length) {
          existing.description = entity.description;
        }
      } else {
        roleMap.set(entity.name, {
          id: entity.name,
          name: entity.name,
          aliases: [...entity.alias],
          power: entity.power,
          description: entity.description,
          descriptions: entity.description ? [entity.description] : [],
          appearances: 1,
          juans: [entity.juan_index],
        });
      }
    });
  });
  
  return roleMap;
}

// Build relationship links between roles
export function buildRoleLinks(data: JuanData): RoleLink[] {
  const linkMap = new Map<string, RoleLink>();
  
  Object.values(data).forEach((extraction: Extraction) => {
    extraction.relations.forEach((relation: Action) => {
      if (relation.is_commentary) return; // Skip commentary
      
      relation.from_roles.forEach((fromRole) => {
        relation.to_roles.forEach((toRole) => {
          const key = `${fromRole}->${toRole}`;
          const existing = linkMap.get(key);
          if (existing) {
            existing.weight += 1;
          } else {
            linkMap.set(key, {
              source: fromRole,
              target: toRole,
              action: relation.action,
              weight: 1,
              time: relation.time,
            });
          }
        });
      });
    });
  });
  
  return Array.from(linkMap.values());
}

// Extract timeline events
export function extractTimelineEvents(data: JuanData): TimelineEvent[] {
  const events: TimelineEvent[] = [];
  
  Object.entries(data).forEach(([key, extraction]: [string, Extraction]) => {
    // Add named events
    extraction.events.forEach((event: Event, idx: number) => {
      events.push({
        id: `${key}-event-${idx}`,
        name: event.name,
        time: event.time,
        timeNumeric: parseChineseYear(event.time),
        location: event.location,
        participants: event.participants,
        description: event.description,
        juan_index: extraction.juan_index,
        segment_index: extraction.segment_index,
        type: 'event',
      });
    });
    
    // Add significant actions as timeline events
    extraction.relations
      .filter((r) => !r.is_commentary && r.event_name)
      .forEach((relation: Action, idx: number) => {
        events.push({
          id: `${key}-action-${idx}`,
          name: relation.event_name || relation.action,
          time: relation.time,
          timeNumeric: parseChineseYear(relation.time),
          location: relation.location,
          participants: [...relation.from_roles, ...relation.to_roles],
          description: relation.context,
          juan_index: extraction.juan_index,
          segment_index: extraction.segment_index,
          type: 'action',
        });
      });
  });
  
  // Sort by time
  return events.sort((a, b) => {
    if (a.timeNumeric === null && b.timeNumeric === null) return 0;
    if (a.timeNumeric === null) return 1;
    if (b.timeNumeric === null) return -1;
    return a.timeNumeric - b.timeNumeric;
  });
}

// Aggregate locations
export function aggregateLocations(data: JuanData): Location[] {
  const locationMap = new Map<string, Location>();
  
  Object.values(data).forEach((extraction: Extraction) => {
    extraction.locations.forEach((location: Location) => {
      if (!locationMap.has(location.name)) {
        locationMap.set(location.name, location);
      }
    });
  });
  
  return Array.from(locationMap.values());
}

// Calculate power distribution
export function calculatePowerDistribution(roleMap: Map<string, RoleNode>): PowerDistribution[] {
  const powerMap = new Map<string, PowerDistribution>();
  
  roleMap.forEach((role) => {
    const power = role.power || '无明确势力';
    const existing = powerMap.get(power);
    if (existing) {
      existing.count += 1;
      existing.roles.push(role.name);
    } else {
      powerMap.set(power, {
        power,
        count: 1,
        roles: [role.name],
      });
    }
  });
  
  return Array.from(powerMap.values()).sort((a, b) => b.count - a.count);
}

// Filter data by juan range
export function filterByJuanRange(
  data: JuanData,
  startJuan: number,
  endJuan: number
): JuanData {
  const filtered: JuanData = {};
  
  Object.entries(data).forEach(([key, extraction]) => {
    if (extraction.juan_index >= startJuan && extraction.juan_index <= endJuan) {
      filtered[key] = extraction;
    }
  });
  
  return filtered;
}

// Filter data by time range (BC years as negative numbers)
export function filterByTimeRange(
  events: TimelineEvent[],
  startYear: number | null,
  endYear: number | null
): TimelineEvent[] {
  return events.filter((event) => {
    if (event.timeNumeric === null) return true; // Include events without time
    if (startYear !== null && event.timeNumeric < startYear) return false;
    if (endYear !== null && event.timeNumeric > endYear) return false;
    return true;
  });
}

// Find events, roles, and actions related to a location
export function findLocationRelated(
  data: JuanData,
  locationName: string
): {
  events: TimelineEvent[];
  roles: string[];
  actions: Action[];
} {
  const events: TimelineEvent[] = [];
  const rolesSet = new Set<string>();
  const actions: Action[] = [];

  Object.entries(data).forEach(([key, extraction]) => {
    // Find events at this location
    extraction.events.forEach((event, idx) => {
      if (event.location === locationName) {
        events.push({
          id: `${key}-event-${idx}`,
          name: event.name,
          time: event.time,
          timeNumeric: parseChineseYear(event.time),
          location: event.location,
          participants: event.participants,
          description: event.description,
          juan_index: extraction.juan_index,
          segment_index: extraction.segment_index,
          type: 'event',
        });
        // Add participants as related roles
        event.participants.forEach((p) => rolesSet.add(p));
      }
    });

    // Find actions at this location
    extraction.relations.forEach((action) => {
      if (action.location === locationName) {
        actions.push(action);
        // Add from/to roles as related
        action.from_roles.forEach((r) => rolesSet.add(r));
        action.to_roles.forEach((r) => rolesSet.add(r));
      }
    });

    // Also check locations' related_entities
    extraction.locations.forEach((loc) => {
      if (loc.name === locationName && loc.related_entities) {
        loc.related_entities.forEach((e) => rolesSet.add(e));
      }
    });
  });

  return {
    events,
    roles: Array.from(rolesSet),
    actions,
  };
}

// Type definitions matching the Python models

export * from './pipelineArtifacts';

export interface Role {
  name: string;
  alias: string[];
  original_description_in_book: string;
  description: string;
  power: string | null;
  sentence_indexes_in_segment: number[];
  juan_index: number;
  segment_index: number;
}

export interface Location {
  name: string;
  alias: string[];
  type: string;
  description: string;
  modern_name: string;
  coordinates: [number, number] | null;
  related_entities: string[];
  sentence_indexes_in_segment: number[];
  juan_index: number;
  segment_index: number;
}

export interface Action {
  time: string | null;
  from_roles: string[];
  to_roles: string[];
  action: string;
  context: string;
  result: string | null;
  event_name: string | null;
  location: string | null;
  is_commentary: boolean;
  sentence_indexes_in_segment: number[];
  juan_index: number;
  segment_index: number;
}

export interface Event {
  name: string;
  time: string | null;
  location: string | null;
  participants: string[];
  description: string;
  background: string;
  significance: string;
  related_action_indices: number[];
  source: string;
  sentence_indexes_in_segment: number[];
  juan_index: number;
  segment_index: number;
}

export interface Extraction {
  juan_index: number;
  segment_index: number;
  chunk_start_index: number;
  chunk_end_index: number;
  segment_start_time: string;
  source_sentences: string[];
  entities: Role[];
  locations: Location[];
  events: Event[];
  relations: Action[];
  extracted_at: string;
  model_name: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

export interface JuanData {
  [key: string]: Extraction;
}

export interface Metadata {
  title: string;
  total_juans: number;
  extracted_juans: number[];
  last_updated: string;
}

// Aggregated data structures for visualization
export interface RoleNode {
  id: string;
  name: string;
  aliases: string[];
  power: string | null;
  description: string;
  descriptions: string[]; // Multiple descriptions from different sources
  appearances: number;
  juans: number[];
}

export interface RoleLink {
  source: string;
  target: string;
  action: string;
  weight: number;
  time: string | null;
}

export interface TimelineEvent {
  id: string;
  name: string;
  time: string | null;
  timeNumeric: number | null; // For sorting, e.g., -403 for 前403年
  location: string | null;
  participants: string[];
  description: string;
  juan_index: number;
  segment_index: number;
  type: 'event' | 'action';
}

export interface PowerDistribution {
  power: string;
  count: number;
  roles: string[];
}

// Re-export unified types
export * from './unified';

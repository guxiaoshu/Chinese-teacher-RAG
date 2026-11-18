import { useMemo, useEffect, useRef, useState } from 'react';
import { MapContainer, TileLayer, CircleMarker, Polyline, Popup, useMap } from 'react-leaflet';
import type { Map as LeafletMap } from 'leaflet';
import 'leaflet/dist/leaflet.css';
import type { TimelineEventUnified, RoleNodeUnified, UnifiedLocation } from '../types/unified';

interface MapViewProps {
  locations: UnifiedLocation[];
  eventsInRange: TimelineEventUnified[];
  selectedRole: RoleNodeUnified | null;
  selectedEvent: TimelineEventUnified | null;
  focusLocationId?: string | null;
  onLocationClick?: (location: UnifiedLocation) => void;
}

type TrajectoryPoint = {
  id: string;
  name: string;
  lng: number;
  lat: number;
  eventId: string;
  eventName: string;
  year: number | null;
};

// Auto-fit map bounds when locations change
function FitBounds({ locations }: { locations: UnifiedLocation[] }) {
  const map = useMap();
  const fittedRef = useRef(false);

  useEffect(() => {
    const withCoords = locations.filter((loc) => loc.coordinates);
    if (withCoords.length === 0) return;
    if (fittedRef.current) return; // Only fit once initially

    const bounds = withCoords.map((loc) => [loc.coordinates![1], loc.coordinates![0]] as [number, number]);
    map.fitBounds(bounds, { padding: [30, 30], maxZoom: 8 });
    fittedRef.current = true;
  }, [locations, map]);

  return null;
}

function FocusLocation({ location }: { location: UnifiedLocation | null }) {
  const map = useMap();
  useEffect(() => {
    if (!location?.coordinates) return;
    const [lng, lat] = location.coordinates;
    // Zoom in enough to make the target obvious, but not too close.
    map.setView([lat, lng], Math.max(map.getZoom(), 8), { animate: true });
  }, [location, map]);
  return null;
}

export function MapView({
  locations,
  eventsInRange,
  selectedRole,
  selectedEvent,
  focusLocationId,
  onLocationClick,
}: MapViewProps) {
  const mapRef = useRef<LeafletMap | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [selectedLocation, setSelectedLocation] = useState<UnifiedLocation | null>(null);

  const byName = useMemo(() => {
    const m = new Map<string, UnifiedLocation>();
    for (const loc of locations) m.set(loc.canonical_name, loc);
    return m;
  }, [locations]);

  const withCoords = useMemo(() => locations.filter((loc) => loc.coordinates), [locations]);

  const focusLocation = useMemo(() => {
    if (!focusLocationId) return null;
    return withCoords.find((l) => l.id === focusLocationId) ?? null;
  }, [withCoords, focusLocationId]);

  useEffect(() => {
    if (!focusLocation) return;
    setSelectedLocation(focusLocation);
  }, [focusLocation]);

  // Compute trajectory for selected role/event
  const trajectory = useMemo((): TrajectoryPoint[] => {
    if (!selectedRole && !selectedEvent) return [];

    const candidates = selectedEvent
      ? [selectedEvent]
      : eventsInRange.filter((e) => e.participants?.includes(selectedRole!.name));

    const points: TrajectoryPoint[] = [];
    for (const ev of candidates) {
      if (ev.timeNumeric === null) continue;
      if (!ev.location) continue;
      const loc = byName.get(ev.location);
      if (!loc?.coordinates) continue;
      points.push({
        id: `${ev.id}:${loc.id}`,
        name: loc.canonical_name,
        lng: loc.coordinates[0],
        lat: loc.coordinates[1],
        eventId: ev.id,
        eventName: ev.name,
        year: ev.timeNumeric,
      });
    }

    points.sort((a, b) => (a.year ?? 0) - (b.year ?? 0));
    return points;
  }, [selectedRole, selectedEvent, eventsInRange, byName]);

  const trajectoryLine = useMemo(() => {
    if (trajectory.length < 2) return null;
    return trajectory.map((p) => [p.lat, p.lng] as [number, number]);
  }, [trajectory]);

  // Compute center from all locations with coordinates
  const { center, zoom } = useMemo(() => {
    if (withCoords.length === 0) {
      // Fallback: central China
      return { center: [34.5, 108.9] as [number, number], zoom: 5 };
    }
    let sumLat = 0, sumLng = 0;
    for (const loc of withCoords) {
      sumLng += loc.coordinates![0];
      sumLat += loc.coordinates![1];
    }
    const avgLat = sumLat / withCoords.length;
    const avgLng = sumLng / withCoords.length;
    return { center: [avgLat, avgLng] as [number, number], zoom: 5 };
  }, [withCoords]);

  return (
    <div className="bg-white rounded-lg shadow-md p-4 flex flex-col h-full">
      <div className="flex items-center justify-between mb-4 flex-shrink-0">
        <h3 className="text-lg font-bold text-[#2c1810]">历史地图</h3>
        <div className="text-sm text-gray-500">
          {withCoords.length} 个地点
        </div>
      </div>

      <div className="flex-1 flex gap-4 overflow-hidden" style={{ minHeight: '500px' }}>
        {/* Map container */}
        <div className="flex-1 rounded-lg overflow-hidden border border-[#d4c5b5]">
          <MapContainer
            center={center}
            zoom={zoom}
            className="w-full h-full"
            style={{ minHeight: '500px' }}
            ref={mapRef}
          >
            {/* OpenStreetMap tiles - neutral, shows rivers/mountains, no border issues */}
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />

            <FitBounds locations={locations} />
            <FocusLocation location={focusLocation} />

            {/* Trajectory polyline */}
            {trajectoryLine && (
              <Polyline
                positions={trajectoryLine}
                pathOptions={{
                  color: '#8b4513',
                  weight: 3,
                  opacity: 0.8,
                  dashArray: '8, 4',
                }}
              />
            )}

            {/* Location markers */}
            {withCoords.map((loc) => (
              <CircleMarker
                key={loc.id}
                center={[loc.coordinates![1], loc.coordinates![0]]}
                radius={hoveredId === loc.id || selectedLocation?.id === loc.id ? 9 : 6}
                pathOptions={{
                  fillColor: selectedLocation?.id === loc.id ? '#8b4513' : '#c41e3a',
                  color: '#8b4513',
                  weight: selectedLocation?.id === loc.id ? 3 : 1,
                  opacity: 1,
                  fillOpacity: 0.85,
                }}
                eventHandlers={{
                  click: () => setSelectedLocation(loc),
                  mouseover: () => setHoveredId(loc.id),
                  mouseout: () => setHoveredId(null),
                }}
              >
                <Popup>
                  <div className="text-sm">
                    <div className="font-bold text-[#8b4513]">{loc.canonical_name}</div>
                    {loc.modern_name && (
                      <div className="text-gray-600">今：{loc.modern_name}</div>
                    )}
                    {loc.location_type && (
                      <div className="text-gray-500 text-xs">{loc.location_type}</div>
                    )}
                  </div>
                </Popup>
              </CircleMarker>
            ))}

            {/* Trajectory waypoints */}
            {trajectory.map((pt, idx) => (
              <CircleMarker
                key={pt.id}
                center={[pt.lat, pt.lng]}
                radius={8}
                pathOptions={{
                  fillColor: '#8b4513',
                  color: '#2c1810',
                  weight: 2,
                  opacity: 1,
                  fillOpacity: 0.95,
                }}
              >
                <Popup>
                  <div className="text-sm">
                    <div className="font-bold text-[#8b4513]">
                      {idx + 1}. {pt.eventName}
                    </div>
                    <div className="text-gray-600">
                      {pt.year !== null ? `${pt.year < 0 ? `前${Math.abs(pt.year)}` : pt.year}年` : '未知年'}
                    </div>
                    <div className="text-gray-500 text-xs">@ {pt.name}</div>
                  </div>
                </Popup>
              </CircleMarker>
            ))}
          </MapContainer>
        </div>

        {/* Detail panel for selected location */}
        {selectedLocation && (
          <div className="w-72 flex-shrink-0 flex flex-col bg-[#faf8f5] rounded-lg border border-[#d4c5b5] p-4 overflow-hidden">
            <div className="flex justify-between items-start mb-3">
              <h4 className="font-bold text-[#8b4513] text-lg">{selectedLocation.canonical_name}</h4>
              <button
                onClick={() => setSelectedLocation(null)}
                className="text-gray-400 hover:text-gray-600 text-xl leading-none"
              >
                ×
              </button>
            </div>
            
            {selectedLocation.modern_name && (
              <p className="text-sm text-gray-600 mb-2">今：{selectedLocation.modern_name}</p>
            )}
            {selectedLocation.location_type && (
              <p className="text-xs text-gray-500 mb-2">类型：{selectedLocation.location_type}</p>
            )}
            {selectedLocation.description && (
              <p className="text-sm text-gray-700 mb-4">{selectedLocation.description}</p>
            )}

            <div className="mt-auto">
              <button
                onClick={() => {
                  onLocationClick?.(selectedLocation);
                }}
                className="w-full px-3 py-2 text-sm bg-[#8b4513] text-white rounded hover:bg-[#5d2e0c] transition-colors"
              >
                查看详情
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Trajectory indicator */}
      {trajectory.length >= 2 && (
        <div className="mt-3 p-2 bg-[#faf8f5] rounded text-sm text-[#8b4513] flex-shrink-0">
          <span className="font-semibold">轨迹：</span>
          {selectedRole ? selectedRole.name : selectedEvent ? selectedEvent.name : ''}{' '}
          ({trajectory.length} 个事件节点)
        </div>
      )}
    </div>
  );
}

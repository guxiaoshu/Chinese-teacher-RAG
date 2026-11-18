import { useState, useEffect } from 'react';
import type { JuanData, Metadata } from '../types';

// In a real application, this would fetch from an API
// For now, we'll load the data statically

export function useHistoricalData() {
  const [data, setData] = useState<JuanData | null>(null);
  const [metadata, setMetadata] = useState<Metadata | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadData() {
      try {
        // Load data from public directory
        const [juanResponse, metadataResponse] = await Promise.all([
          fetch('/data/juan_1.json'),
          fetch('/data/metadata.json'),
        ]);

        if (!juanResponse.ok || !metadataResponse.ok) {
          throw new Error('Failed to load data files');
        }

        const juanData = await juanResponse.json();
        const metadataData = await metadataResponse.json();

        setData(juanData);
        setMetadata(metadataData);
        setLoading(false);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error');
        setLoading(false);
      }
    }

    loadData();
  }, []);

  return { data, metadata, loading, error };
}

export function useFilteredData(
  data: JuanData | null,
  juanRange: [number, number],
  timeRange: [number | null, number | null]
) {
  const [filteredData, setFilteredData] = useState<JuanData | null>(null);

  useEffect(() => {
    if (!data) {
      setFilteredData(null);
      return;
    }

    const filtered: JuanData = {};
    Object.entries(data).forEach(([key, extraction]) => {
      const inJuanRange =
        extraction.juan_index >= juanRange[0] &&
        extraction.juan_index <= juanRange[1];

      if (inJuanRange) {
        filtered[key] = extraction;
      }
    });

    setFilteredData(filtered);
  }, [data, juanRange, timeRange]);

  return filteredData;
}

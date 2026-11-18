import { useEffect, useState } from 'react';

export interface JuanYearIndex {
  version: string;
  generated_at: string;
  juan_start_year: Record<string, number>;
}

export function useJuanYearIndex() {
  const [juanYearIndex, setJuanYearIndex] = useState<JuanYearIndex | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const response = await fetch('/data/juan_year_index.json');
        if (!response.ok) {
          throw new Error(`Failed to load juan year index: ${response.status}`);
        }
        const data = (await response.json()) as JuanYearIndex;
        setJuanYearIndex(data);
        setLoading(false);
      } catch (err) {
        console.error('Error loading juan year index:', err);
        setError(err instanceof Error ? err.message : 'Unknown error loading juan year index');
        setLoading(false);
      }
    }

    load();
  }, []);

  return { juanYearIndex, loading, error };
}

/**
 * Smartacus Shortlist Hook
 * ========================
 *
 * Hook pour fetcher et gérer la shortlist d'opportunités.
 */

import { useState, useEffect, useCallback } from 'react';
import { ShortlistResponse, PipelineStatus } from '@/types/opportunity';
import { api } from '@/lib/api';

interface UseShortlistOptions {
  maxItems?: number;
  minScore?: number;
  minValue?: number;
  pollingInterval?: number; // in milliseconds
}

interface UseShortlistReturn {
  shortlist: ShortlistResponse | null;
  pipelineStatus: PipelineStatus | null;
  isLoading: boolean;
  error: Error | null;
  refetch: () => Promise<void>;
}

export function useShortlist(options: UseShortlistOptions = {}): UseShortlistReturn {
  const [shortlist, setShortlist] = useState<ShortlistResponse | null>(null);
  const [pipelineStatus, setPipelineStatus] = useState<PipelineStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const fetchData = useCallback(async () => {
    try {
      setError(null);

      // Fetch both in parallel
      const [shortlistData, statusData] = await Promise.all([
        api.getShortlist({
          maxItems: options.maxItems,
          minScore: options.minScore,
          minValue: options.minValue,
        }),
        api.getPipelineStatus(),
      ]);

      setShortlist(shortlistData);
      setPipelineStatus(statusData);
    } catch (err) {
      console.error('Error fetching shortlist:', err);
      setError(err instanceof Error ? err : new Error('Unknown error'));
    } finally {
      setIsLoading(false);
    }
  }, [options.maxItems, options.minScore, options.minValue]);

  // Initial fetch
  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Optional polling
  useEffect(() => {
    if (!options.pollingInterval) return;

    const interval = setInterval(fetchData, options.pollingInterval);
    return () => clearInterval(interval);
  }, [fetchData, options.pollingInterval]);

  return {
    shortlist,
    pipelineStatus,
    isLoading,
    error,
    refetch: fetchData,
  };
}

export default useShortlist;

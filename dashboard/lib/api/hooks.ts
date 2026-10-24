"use client";

/** Polling hooks. About once a second, no WebSockets (task doc → step 3). */

import { useCallback, useEffect, useRef, useState } from "react";

import { useLang } from "@/lib/i18n";

import { api, DATA_MODE } from "./client";
import { subscribe } from "./fixtures";
import type { FeedItem } from "./types";

export interface Polled<T> {
  data: T | null;
  error: Error | null;
  /** Refetch now, e.g. after a delete. */
  refresh: () => void;
}

/**
 * Calls `load` now, every `intervalMs`, and whenever `key` changes. Keeps the last
 * good data on errors, so a blip doesn't blank the screen during a recording.
 */
export function usePoll<T>(load: () => Promise<T>, key: string, intervalMs = 1000): Polled<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const loadRef = useRef(load);
  loadRef.current = load;
  const [tick, setTick] = useState(0);
  const refresh = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    setData(null);
  }, [key]);

  useEffect(() => {
    let alive = true;
    const run = () =>
      loadRef.current().then(
        (value) => {
          if (!alive) return;
          setData(value);
          setError(null);
        },
        (err: unknown) => {
          if (alive) setError(err instanceof Error ? err : new Error(String(err)));
        },
      );
    run();
    const timer = setInterval(run, intervalMs);
    const unsubscribe = DATA_MODE === "fixtures" ? subscribe(run) : () => {};
    return () => {
      alive = false;
      clearInterval(timer);
      unsubscribe();
    };
  }, [key, intervalMs, tick]);

  return { data, error, refresh };
}

/**
 * The user's feed, oldest first. Polls with `since` set to the newest item's time
 * and appends; starts over when the language changes (the text is per language).
 */
export function useFeed(userId: string): { items: FeedItem[]; error: Error | null } {
  const { lang } = useLang();
  const [items, setItems] = useState<FeedItem[]>([]);
  const [error, setError] = useState<Error | null>(null);
  const [epoch, setEpoch] = useState(0);

  useEffect(() => {
    // Fixture steps can move backwards, so refetch the whole feed when they change.
    return DATA_MODE === "fixtures" ? subscribe(() => setEpoch((e) => e + 1)) : undefined;
  }, []);

  useEffect(() => {
    let alive = true;
    let since: string | null = null;
    setItems([]);
    const run = () =>
      api.feed(userId, since, lang).then(
        (fresh) => {
          if (!alive) return;
          setError(null);
          if (!fresh.length) return;
          since = fresh[fresh.length - 1].at;
          setItems((prev) => {
            const seen = new Set(prev.map((i) => i.id));
            return [...prev, ...fresh.filter((i) => !seen.has(i.id))];
          });
        },
        (err: unknown) => {
          if (alive) setError(err instanceof Error ? err : new Error(String(err)));
        },
      );
    run();
    const timer = setInterval(run, 1000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [userId, lang, epoch]);

  return { items, error };
}

/** A clock that re-renders every second, for hold timers and relative times. */
export function useNow(intervalMs = 1000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(timer);
  }, [intervalMs]);
  return now;
}

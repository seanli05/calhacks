"use client";

/** Polling hooks. About once a second, no WebSockets (task doc → step 3). */

import { useCallback, useEffect, useRef, useState } from "react";

import { useLang } from "@/lib/i18n";

import { api, DATA_MODE } from "./client";
import { subscribe } from "./fixtures";
import type { FeedItem, LiveTip, Speaker } from "./types";

/**
 * Runs `task` now, then again `intervalMs` after each run settles. Never overlaps,
 * so a slow API gets one request at a time instead of a growing pile. Returns stop.
 */
function repeat(task: () => Promise<unknown>, intervalMs: number): () => void {
  let stopped = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const loop = () => {
    task().finally(() => {
      if (!stopped) timer = setTimeout(loop, intervalMs);
    });
  };
  loop();
  return () => {
    stopped = true;
    clearTimeout(timer);
  };
}

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
    const stop = repeat(run, intervalMs);
    const unsubscribe = DATA_MODE === "fixtures" ? subscribe(run) : () => {};
    return () => {
      alive = false;
      stop();
      unsubscribe();
    };
  }, [key, intervalMs, tick]);

  return { data, error, refresh };
}

/**
 * The user's feed, oldest first. Polls with `since` set to the newest item's time
 * and appends; starts over when the language changes (the text is per language).
 * `steps` adds the step logs behind each task (the case view's live activity).
 * Text without a template is translated in the background (Dari), so while any
 * line is still in English the whole feed is fetched again every few seconds.
 */
/** Polls between full refetches while feed text still waits for its translation. */
const RETRANSLATE_EVERY = 3;

export function useFeed(userId: string, steps = false): { items: FeedItem[]; error: Error | null } {
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
    let untranslated = false;
    let tick = 0;
    setItems([]);
    const run = () => {
      const refetch = untranslated && tick++ % RETRANSLATE_EVERY === 0;
      return api.feed(userId, refetch ? null : since, lang, steps).then(
        (fresh) => {
          if (!alive) return;
          setError(null);
          if (!fresh.length) return;
          since = fresh[fresh.length - 1].at;
          setItems((prev) => {
            const seen = new Set(prev.map((i) => i.id));
            const next = refetch ? fresh : [...prev, ...fresh.filter((i) => !seen.has(i.id))];
            untranslated = lang !== "en" && next.some((i) => !i.step && i.text.text === i.text.en);
            return next;
          });
        },
        (err: unknown) => {
          if (alive) setError(err instanceof Error ? err : new Error(String(err)));
        },
      );
    };
    const stop = repeat(run, 1000);
    return () => {
      alive = false;
      stop();
    };
  }, [userId, lang, epoch, steps]);

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

export interface LiveLine {
  id: string;
  at: string;
  speaker: Speaker;
  en: string;
  /** The translation so far. */
  text: string;
  done: boolean;
}

export interface LiveCall {
  lines: LiveLine[];
  tips: (LiveTip & { used: boolean })[];
}

/**
 * The bridged call as it streams in, while `active`. Starts over when the call or
 * the language changes, since every line is translated for one language.
 */
export function useLiveCall(callId: string | null, active: boolean): LiveCall {
  const { lang } = useLang();
  const [live, setLive] = useState<LiveCall>({ lines: [], tips: [] });

  useEffect(() => {
    setLive({ lines: [], tips: [] });
    if (!callId || !active) return;
    return api.liveCall(callId, lang, (event) =>
      setLive((prev) => {
        switch (event.type) {
          case "line": {
            // A reconnect replays the call: start the known line over in place.
            const line = { ...event, text: "", done: false };
            return prev.lines.some((l) => l.id === event.id)
              ? { ...prev, lines: prev.lines.map((l) => (l.id === event.id ? line : l)) }
              : { ...prev, lines: [...prev.lines, line] };
          }
          case "delta":
            return {
              ...prev,
              lines: prev.lines.map((l) => (l.id === event.id ? { ...l, text: l.text + event.text } : l)),
            };
          case "done":
            return { ...prev, lines: prev.lines.map((l) => (l.id === event.id ? { ...l, done: true } : l)) };
          case "tip":
            return prev.tips.some((t) => t.id === event.tip.id)
              ? prev
              : { ...prev, tips: [...prev.tips, { ...event.tip, used: false }] };
          case "tip_used":
            return { ...prev, tips: prev.tips.map((t) => (t.id === event.id ? { ...t, used: true } : t)) };
        }
      }),
    );
  }, [callId, active, lang]);

  return live;
}

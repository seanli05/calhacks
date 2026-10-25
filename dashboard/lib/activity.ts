/**
 * Folds the case feed into tasks for the live activity: a research job (by
 * `job_id`) or a call (by `call_id`) becomes one card holding its steps, the rest
 * stay plain feed items. A task that finished without any steps (the fast read of
 * the letter) stays plain items too, as before.
 */

import type { FeedItem } from "./api/types";

export interface Task {
  id: string;
  /** What the card's header says: the result once done, the latest news before. */
  title: FeedItem;
  /** Everything else in the task, oldest first. */
  rows: FeedItem[];
  steps: number;
  running: boolean;
  startedAt: string;
  endedAt: string;
}

export type ActivityEntry = { kind: "item"; item: FeedItem } | { kind: "task"; task: Task };

const END_TYPES = new Set([
  "research.fast_done",
  "research.fast_failed",
  "research.deep_done",
  "research.deep_failed",
  "research.needs_user_input",
  "research.question_done",
  "research.question_failed",
  "call.ended",
  "call.user_unreachable",
]);

/** A research task with no news for this long has stalled: no spinner. A call
 * can sit on hold far longer without news, so it runs until it ends. */
export const STALL_MS = 10 * 60_000;

function taskKey(item: FeedItem): string | null {
  if (item.type.startsWith("call.")) return item.call_id ? `call:${item.call_id}` : null;
  if (item.type.startsWith("research.") || item.type.startsWith("verification.")) {
    return item.job_id ? `job:${item.job_id}` : null;
  }
  return null;
}

export function groupActivity(items: FeedItem[], now: number): ActivityEntry[] {
  const groups = new Map<string, FeedItem[]>();
  const order: (string | FeedItem)[] = [];
  for (const item of items) {
    const key = taskKey(item);
    if (!key) {
      order.push(item);
      continue;
    }
    const group = groups.get(key);
    if (group) group.push(item);
    else {
      groups.set(key, [item]);
      order.push(key);
    }
  }

  const entries: ActivityEntry[] = [];
  for (const slot of order) {
    if (typeof slot !== "string") {
      entries.push({ kind: "item", item: slot });
      continue;
    }
    const group = groups.get(slot)!;
    const task = toTask(slot, group, now);
    if (task) entries.push({ kind: "task", task });
    else for (const item of group) entries.push({ kind: "item", item });
  }
  return entries;
}

function toTask(id: string, group: FeedItem[], now: number): Task | null {
  const steps = group.filter((i) => i.step).length;
  const ended = group.some((i) => END_TYPES.has(i.type));
  if (ended && steps === 0) return null;
  const news = group.filter((i) => !i.step);
  const verdict = [...news].reverse().find((i) => i.type.startsWith("verification."));
  const lastEnd = [...news].reverse().find((i) => END_TYPES.has(i.type));
  const title = (ended ? (verdict ?? lastEnd) : news[news.length - 1]) ?? group[group.length - 1];
  const last = group[group.length - 1];
  return {
    id,
    title,
    rows: group.filter((i) => i !== title && !(ended && END_TYPES.has(i.type))),
    steps,
    running: !ended && (id.startsWith("call:") || now - Date.parse(last.at) < STALL_MS),
    startedAt: group[0].at,
    endedAt: last.at,
  };
}

/** "0:41" or "12:05". */
export function elapsed(fromIso: string, toMs: number): string {
  const s = Math.max(0, Math.floor((toMs - Date.parse(fromIso)) / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

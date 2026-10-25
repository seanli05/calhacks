"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { Icon, iconForEvent, type IconName } from "@/components/Icon";
import { elapsed, groupActivity, type Task } from "@/lib/activity";
import { useNow } from "@/lib/api/hooks";
import type { FeedItem } from "@/lib/api/types";
import { relativeTime, shortDate } from "@/lib/format";
import { useLang, useStrings } from "@/lib/i18n";
import { englishBelow } from "@/lib/localized";

import styles from "./ActivityFeed.module.css";

/** How long a finished task stays open before it folds into one line. */
const COLLAPSE_AFTER_MS = 1200;

/**
 * The case feed with its work shown as it happens: each research check or call is
 * a card whose steps (searches, pages read, checks, menus heard) stream in while it
 * runs, then fold away behind the result. Newest at the bottom, like `FeedList`.
 * Each step shows its why (`step.reason`) on a short line under it.
 */
export function ActivityFeed({ items, className = "" }: { items: FeedItem[]; className?: string }) {
  const t = useStrings().case.activity;
  const now = useNow(1000);
  const entries = useMemo(() => groupActivity(items, now), [items, now]);
  const busy = entries.some((e) => e.kind === "task" && e.task.running);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const wrap = wrapRef.current;
    if (wrap) wrap.scrollTop = wrap.scrollHeight;
  }, [items.length]);

  return (
    <div ref={wrapRef} className={`${styles.wrap} ${className}`}>
      <div className={styles.head}>
        <span className="label">{t.title}</span>
        {busy && (
          <span className={styles.working}>
            <span className={styles.dot} aria-hidden="true" />
            {t.working}
          </span>
        )}
      </div>
      <ol className={styles.feed} aria-live="polite">
        {entries.map((entry, index) =>
          entry.kind === "task" ? (
            <li key={entry.task.id} className={styles.taskItem}>
              <TaskCard task={entry.task} now={now} />
            </li>
          ) : (
            <PlainItem key={entry.item.id} item={entry.item} now={now} last={index === entries.length - 1} />
          ),
        )}
      </ol>
    </div>
  );
}

function PlainItem({ item, now, last }: { item: FeedItem; now: number; last: boolean }) {
  const { lang } = useLang();
  const t = useStrings().common;
  return (
    <li className={`${styles.item} ${last ? styles.latest : ""}`}>
      <span className={styles.ic}>
        <Icon name={iconForEvent(item.type)} />
      </span>
      <span className={styles.what}>
        {item.text.text}
        {item.deleted_at && <span className={styles.deleted}> {t.deleted(shortDate(item.deleted_at, lang))}</span>}
        {englishBelow(item.text, lang) && <small>{item.text.en}</small>}
      </span>
      <span className={styles.when}>{relativeTime(item.at, lang, now)}</span>
    </li>
  );
}

function TaskCard({ task, now }: { task: Task; now: number }) {
  const { lang } = useLang();
  const t = useStrings().case.activity;
  const [open, setOpen] = useState(task.running);
  const [touched, setTouched] = useState(false);
  const wasRunning = useRef(task.running);

  useEffect(() => {
    if (task.running) {
      wasRunning.current = true;
      if (!touched) setOpen(true);
      return;
    }
    if (!wasRunning.current || touched) return;
    wasRunning.current = false;
    const timer = setTimeout(() => setOpen(false), COLLAPSE_AFTER_MS);
    return () => clearTimeout(timer);
  }, [task.running, touched]);

  const warn = !task.running && (iconForEvent(task.title.type) === "warn" || task.title.type.endsWith("_failed"));
  const time = elapsed(task.startedAt, task.running ? now : Date.parse(task.endedAt));
  const meta = [t.steps(task.steps), time, !task.running && !open ? t.show : null].filter(Boolean).join(" · ");
  const bodyId = `${task.id}-steps`;

  return (
    <div className={`${styles.task} ${task.running ? styles.running : ""} ${open ? styles.open : ""}`}>
      <button
        type="button"
        className={styles.taskHead}
        aria-expanded={open}
        aria-controls={bodyId}
        aria-label={`${task.title.text.text}. ${open ? t.hide : t.show}`}
        onClick={() => {
          setTouched(true);
          setOpen((o) => !o);
        }}
      >
        <span className={`${styles.badge} ${task.running ? "" : warn ? styles.badgeWarn : styles.badgeDone}`}>
          {task.running ? <span className={styles.spin} aria-hidden="true" /> : <Icon name={warn ? "warn" : "check"} size={14} />}
        </span>
        <span className={styles.title}>
          <span className={task.running ? styles.shimmer : ""}>{task.title.text.text}</span>
          {englishBelow(task.title.text, lang) && <small>{task.title.text.en}</small>}
        </span>
        <span className={styles.meta}>{meta}</span>
        <span className={styles.chev}>
          <Icon name="chevron" size={14} />
        </span>
      </button>
      <div id={bodyId} className={styles.body}>
        <ol className={styles.steps}>
          {task.rows.map((row, i) => (
            <StepRow key={row.id} row={row} active={task.running && i === task.rows.length - 1} />
          ))}
        </ol>
      </div>
    </div>
  );
}

const STEP_ICONS: Record<string, IconName> = {
  "research.search": "search",
  "research.fetch": "doc",
  "research.check": "shield",
  "call.menu_heard": "wave",
};

function StepRow({ row, active }: { row: FeedItem; active: boolean }) {
  const { lang } = useLang();
  const t = useStrings().case.activity;
  const step = row.step;
  const icon = STEP_ICONS[row.type] ?? iconForEvent(row.type);
  if (!step) {
    return (
      <li className={`${styles.row} ${styles.news} ${active ? styles.active : ""}`}>
        <span className={styles.ri}>
          <Icon name={icon} size={14} />
        </span>
        <span className={styles.newsText}>
          {row.text.text}
          {englishBelow(row.text, lang) && <small>{row.text.en}</small>}
        </span>
        {active && <span className={styles.spin} aria-hidden="true" />}
      </li>
    );
  }
  const tone = step.ok === false ? styles.bad : step.ok ? styles.good : "";
  return (
    <li className={`${styles.row} ${active ? styles.active : ""}`}>
      <span className={styles.ri}>
        <Icon name={icon} size={14} />
      </span>
      <span className={styles.action}>{step.action.text}</span>
      <span className={styles.detail}>{step.detail}</span>
      {active ? (
        <span className={styles.spin} aria-hidden="true" />
      ) : (
        step.result && <span className={`${styles.result} ${tone}`}>{step.result.text}</span>
      )}
      {step.reason && (
        <span className={styles.why} lang="en">
          <b>{t.why}:</b> {step.reason}
        </span>
      )}
    </li>
  );
}

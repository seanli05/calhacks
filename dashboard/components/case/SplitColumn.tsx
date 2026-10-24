"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import styles from "./SplitColumn.module.css";

const MIN = 0.5;
const MAX = 0.75;
const DEFAULT = 0.6;
const STEP = 0.05;

const clamp = (v: number) => Math.min(MAX, Math.max(MIN, v));

function readStored(key: string): number | null {
  try {
    const v = Number(window.localStorage.getItem(key));
    return v ? clamp(v) : null;
  } catch {
    return null;
  }
}

function store(key: string, value: number): void {
  try {
    window.localStorage.setItem(key, String(value));
  } catch {
    // Private windows can refuse storage; the split just isn't remembered.
  }
}

/**
 * Two stacked panes with a drag bar between them. `share` is the bottom pane's part
 * of the height, kept between half and three quarters so the top always shows
 * enough to tell which case this is. Arrow keys move it, double-click resets, and
 * the browser remembers it. Stacked layouts (narrow screens) drop the bar.
 */
export function SplitColumn({
  top,
  bottom,
  label,
  storageKey,
}: {
  top: React.ReactNode;
  bottom: React.ReactNode;
  label: string;
  storageKey: string;
}) {
  const [share, setShare] = useState(DEFAULT);
  const boxRef = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);

  useEffect(() => {
    const stored = readStored(storageKey);
    if (stored) setShare(stored);
  }, [storageKey]);

  const update = useCallback(
    (next: number) => {
      const v = clamp(next);
      setShare(v);
      store(storageKey, v);
    },
    [storageKey],
  );

  const onPointerMove = (e: React.PointerEvent) => {
    const box = boxRef.current?.getBoundingClientRect();
    if (!dragging.current || !box) return;
    update(1 - (e.clientY - box.top) / box.height);
  };

  return (
    <div className={`card ${styles.split}`} ref={boxRef}>
      <div className={styles.top} style={{ flexGrow: 1 - share }}>
        {top}
      </div>
      <div
        className={styles.bar}
        role="separator"
        aria-orientation="horizontal"
        aria-label={label}
        aria-valuemin={MIN * 100}
        aria-valuemax={MAX * 100}
        aria-valuenow={Math.round(share * 100)}
        tabIndex={0}
        onPointerDown={(e) => {
          dragging.current = true;
          e.currentTarget.setPointerCapture(e.pointerId);
        }}
        onPointerMove={onPointerMove}
        onPointerUp={() => (dragging.current = false)}
        onPointerCancel={() => (dragging.current = false)}
        onDoubleClick={() => update(DEFAULT)}
        onKeyDown={(e) => {
          if (e.key === "ArrowUp") update(share + STEP);
          else if (e.key === "ArrowDown") update(share - STEP);
          else return;
          e.preventDefault();
        }}
      >
        <span className={styles.grip} />
      </div>
      <div className={styles.bottom} style={{ flexGrow: share }}>
        {bottom}
      </div>
    </div>
  );
}

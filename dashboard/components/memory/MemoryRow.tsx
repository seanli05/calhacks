"use client";

import { useStrings } from "@/lib/i18n";

import styles from "./MemoryRow.module.css";

/** How long a deleted row takes to fade and fold away; the delete call waits for it. */
export const FADE_MS = 600;

/** One deletable thing: its content on the left, a Delete button on the right. */
export function MemoryRow({
  children,
  leaving,
  failed,
  onDelete,
}: {
  children: React.ReactNode;
  leaving: boolean;
  failed: boolean;
  onDelete: () => void;
}) {
  const t = useStrings().memory;
  return (
    <li className={`${styles.row} ${leaving ? styles.leaving : ""}`} aria-hidden={leaving || undefined}>
      <div className={styles.inner}>
        <div className={styles.body}>
          {children}
          {failed && (
            <span className={styles.failed} role="alert">
              {t.deleteFailed}
            </span>
          )}
        </div>
        <button type="button" className="btn danger" onClick={onDelete} disabled={leaving}>
          {t.delete}
        </button>
      </div>
    </li>
  );
}

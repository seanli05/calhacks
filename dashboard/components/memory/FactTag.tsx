"use client";

import { Icon } from "@/components/Icon";
import { useStrings } from "@/lib/i18n";

import styles from "./FactTag.module.css";

/** One saved fact as a square tag: the fact, where it came from, and a × to remove it. */
export function FactTag({
  text,
  english,
  meta,
  isPrivate,
  pending,
  leaving,
  failed,
  onDelete,
}: {
  text: string;
  english: string | null;
  meta: string;
  isPrivate: boolean;
  pending: boolean;
  leaving: boolean;
  failed: boolean;
  onDelete: () => void;
}) {
  const t = useStrings().memory;
  return (
    <li
      className={`${styles.tag} ${pending ? styles.pending : ""} ${leaving ? styles.leaving : ""}`}
      aria-hidden={leaving || undefined}
    >
      <div className={styles.body}>
        <span className={styles.text} dir="auto">
          {text}
        </span>
        {english && <small className={styles.en}>{english}</small>}
        <span className={styles.meta}>
          {isPrivate && (
            <span className={styles.private}>
              <Icon name="lock" size={13} />
              {t.sensitive}
            </span>
          )}
          {pending && <span className="pill warn">{t.pendingConsent}</span>}
          <span>{meta}</span>
        </span>
        {failed && (
          <span className={styles.failed} role="alert">
            {t.deleteFailed}
          </span>
        )}
      </div>
      <button
        type="button"
        className={styles.remove}
        onClick={onDelete}
        disabled={leaving}
        aria-label={t.removeItem(text)}
        title={t.delete}
      >
        <Icon name="close" size={15} />
      </button>
    </li>
  );
}

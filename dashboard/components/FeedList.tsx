"use client";

import { useEffect, useRef } from "react";

import { useNow } from "@/lib/api/hooks";
import type { FeedItem } from "@/lib/api/types";
import { relativeTime, shortDate } from "@/lib/format";
import { useLang, useStrings } from "@/lib/i18n";
import { englishBelow } from "@/lib/localized";

import { Icon, iconForEvent } from "./Icon";
import styles from "./FeedList.module.css";

/**
 * The live feed in the user's language, English muted underneath (unless the UI is
 * in English). Newest at the bottom; the list scrolls itself to the newest item.
 */
export function FeedList({ items, className = "" }: { items: FeedItem[]; className?: string }) {
  const { lang } = useLang();
  const t = useStrings().common;
  const now = useNow(15_000);
  const wrapRef = useRef<HTMLDivElement>(null);
  const lastId = items.length ? items[items.length - 1].id : null;

  useEffect(() => {
    const wrap = wrapRef.current;
    if (wrap) wrap.scrollTop = wrap.scrollHeight;
  }, [lastId]);

  return (
    <div ref={wrapRef} className={`${styles.wrap} ${className}`}>
      <ol className={styles.feed} aria-live="polite">
        {items.map((item) => (
          <li key={item.id}>
            <span className={styles.ic}>
              <Icon name={iconForEvent(item.type)} />
            </span>
            <span className={styles.what} dir="auto">
              {item.text.text}
              {item.deleted_at && (
                <span className={styles.deleted}> {t.deleted(shortDate(item.deleted_at, lang))}</span>
              )}
              {englishBelow(item.text, lang) && <small>{item.text.en}</small>}
            </span>
            <span className={styles.when}>{relativeTime(item.at, lang, now)}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

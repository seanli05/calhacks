"use client";

import { useStrings } from "@/lib/i18n";

import styles from "./CaseTabs.module.css";

export const TABS = ["now", "todo", "words"] as const;
export type Tab = (typeof TABS)[number];

export function isTab(value: string | null): value is Tab {
  return TABS.includes(value as Tab);
}

/**
 * The case sections shown for this case (`tabs`), with `end` (the Messages button)
 * at the far end of the row.
 * `live` puts a pulsing dot on the overview so a running call is findable from any tab.
 */
export function CaseTabs({
  tabs,
  active,
  live,
  onSelect,
  end,
}: {
  tabs: readonly Tab[];
  active: Tab;
  live: boolean;
  onSelect: (tab: Tab) => void;
  end?: React.ReactNode;
}) {
  const t = useStrings().case.tabs;

  return (
    <div className={styles.row}>
      <div className={styles.tabs} role="tablist" aria-label={t.label}>
        {tabs.map((tab) => (
          <button
            key={tab}
            type="button"
            role="tab"
            id={`tab-${tab}`}
            aria-selected={tab === active}
            aria-controls="case-panel"
            className={styles.tab}
            tabIndex={tab === active ? 0 : -1}
            onClick={() => onSelect(tab)}
            onKeyDown={(e) => {
              const step = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
              if (!step) return;
              // The arrows move between tabs here, not anything listening on the page (the fixture bar).
              e.preventDefault();
              e.stopPropagation();
              // Reading direction decides which arrow moves forward (Dari is right to left).
              const rtl = getComputedStyle(e.currentTarget).direction === "rtl";
              const next = tabs[(tabs.indexOf(tab) + (rtl ? -step : step) + tabs.length) % tabs.length];
              onSelect(next);
              document.getElementById(`tab-${next}`)?.focus();
            }}
          >
            {t[tab]}
            {tab === "now" && live && <span className={styles.live} aria-hidden="true" />}
          </button>
        ))}
      </div>
      {end}
    </div>
  );
}

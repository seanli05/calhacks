"use client";

import { useEffect, useRef } from "react";

import { useStrings } from "@/lib/i18n";

import styles from "./Drawer.module.css";

/**
 * A side panel over the case view (the translation book, the letter, the WhatsApp
 * thread), so the page underneath keeps its place. Esc, the close button or the
 * backdrop closes it, and focus goes back to where it was.
 */
export function Drawer({
  label,
  wide = false,
  onClose,
  children,
}: {
  label: string;
  wide?: boolean;
  onClose: () => void;
  children: React.ReactNode;
}) {
  const t = useStrings().case;
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const before = document.activeElement as HTMLElement | null;
    panelRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      before?.focus();
    };
  }, [onClose]);

  return (
    <div className={styles.backdrop} onClick={onClose}>
      <div
        ref={panelRef}
        className={`${styles.panel} ${wide ? styles.wide : ""}`}
        role="dialog"
        aria-modal="true"
        aria-label={label}
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
      >
        <div className={styles.head}>
          <span className="label">{label}</span>
          <button type="button" className={styles.close} onClick={onClose}>
            {t.close} ✕
          </button>
        </div>
        <div className={styles.body}>{children}</div>
      </div>
    </div>
  );
}

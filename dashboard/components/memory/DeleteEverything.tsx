"use client";

import { useEffect, useRef, useState } from "react";

import { useStrings } from "@/lib/i18n";

import styles from "./DeleteEverything.module.css";

/**
 * "Delete everything" with its confirm built into the page (browser `confirm()`
 * would block the demo recording and the browser automation).
 */
export function DeleteEverything({ busy, onConfirm }: { busy: boolean; onConfirm: () => void }) {
  const t = useStrings().memory;
  const [confirming, setConfirming] = useState(false);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const openRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (confirming) cancelRef.current?.focus();
  }, [confirming]);

  const cancel = () => {
    setConfirming(false);
    // Wait for the button to render again before moving focus back to it.
    requestAnimationFrame(() => openRef.current?.focus());
  };

  if (!confirming) {
    return (
      <div className={styles.wrap}>
        <button ref={openRef} type="button" className="btn danger" onClick={() => setConfirming(true)}>
          {t.deleteEverything}
        </button>
      </div>
    );
  }

  return (
    <div
      className={styles.confirm}
      role="alertdialog"
      aria-labelledby="delete-all-title"
      aria-describedby="delete-all-body"
      onKeyDown={(e) => {
        if (e.key === "Escape" && !busy) cancel();
      }}
    >
      <h2 id="delete-all-title">{t.confirm.title}</h2>
      <p id="delete-all-body">{t.confirm.body}</p>
      <div className={styles.actions}>
        <button ref={cancelRef} type="button" className="btn" onClick={cancel} disabled={busy}>
          {t.confirm.cancel}
        </button>
        <button type="button" className={`btn ${styles.yes}`} onClick={onConfirm} disabled={busy}>
          {busy ? t.deleting : t.confirm.yes}
        </button>
      </div>
    </div>
  );
}

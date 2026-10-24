"use client";

import { useState } from "react";

import { mediaUrl } from "@/lib/api/client";

import styles from "./MiniLetter.module.css";

/**
 * A letter thumbnail: the real photo when the API can serve it, otherwise a small
 * drawn page with highlighted lines (fixtures have no image bytes).
 */
export function MiniLetter({ mediaId, width = 96 }: { mediaId: string | null; width?: number }) {
  const [failed, setFailed] = useState(false);
  const src = mediaId ? mediaUrl(mediaId) : null;
  if (src && !failed) {
    // Plain <img>: the bytes come from our own API proxy, so next/image adds nothing.
    return <img src={src} alt="" className={styles.photo} style={{ width }} onError={() => setFailed(true)} />;
  }
  return (
    <div className={styles.page} style={{ width }} aria-hidden="true">
      <i style={{ width: "60%" }} />
      <i />
      <i className={styles.hl} style={{ width: "80%" }} />
      <i />
      <i className={styles.hl} />
      <i style={{ width: "70%" }} />
      <i />
    </div>
  );
}

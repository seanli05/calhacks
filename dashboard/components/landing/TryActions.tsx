"use client";

import Link from "next/link";
import { QRCodeSVG } from "qrcode.react";

import { Icon } from "@/components/Icon";
import { useStrings } from "@/lib/i18n";

import type { TryLinks } from "./useTryLinks";
import styles from "./TryActions.module.css";

/** QR colors are hex because SVG attributes can't read CSS vars (forest on white). */
const QR_FG = "#0e3b2c";

/**
 * "Try it on WhatsApp" + "Watch a live call", and the QR for judges scanning the
 * screen. The QR is hidden on phones, where the button does the same thing.
 */
export function TryActions({ links, qrSize, onDark = false }: { links: TryLinks; qrSize: number; onDark?: boolean }) {
  const t = useStrings().landing;
  return (
    <div className={`${styles.actions} ${onDark ? styles.dark : ""}`}>
      <div className={styles.buttons}>
        {links.join && (
          <a href={links.join} className={`btn primary ${styles.big}`} target="_blank" rel="noreferrer">
            <Icon name="chat" size={19} />
            {t.tryIt}
          </a>
        )}
        {links.demoHref && (
          <Link href={links.demoHref} className={`btn ${styles.big} ${styles.ghost}`}>
            {t.watch}
            <Icon name="arrow" size={19} />
          </Link>
        )}
      </div>
      {links.join && (
        <div className={styles.scan}>
          <div className={styles.qr}>
            <QRCodeSVG value={links.join} size={qrSize} fgColor={QR_FG} bgColor="#ffffff" level="M" title={t.tryIt} />
          </div>
          <div className={styles.scanText}>
            <p className={styles.scanLabel}>{t.scan}</p>
            {links.joinMessage && (
              <>
                <p className={styles.then}>{t.thenSend}</p>
                <p className={`mono ${styles.code}`}>{links.joinMessage}</p>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

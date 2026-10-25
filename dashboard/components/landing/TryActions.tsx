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
 * One main way in ("Try it on WhatsApp"), a quieter "See an example" link, and the QR
 * for people on a computer. The main button always shows, even before the config
 * loads, so the page never has an empty spot where the next step should be.
 * The QR is hidden on phones, where the button does the same thing.
 */
export function TryActions({
  links,
  qrSize,
  scan = true,
  example = true,
}: {
  links: TryLinks;
  qrSize: number;
  /** False in the hero, which stays uncluttered; the closing card carries the QR. */
  scan?: boolean;
  /** False on the example tour itself, where the link would loop back to it. */
  example?: boolean;
}) {
  const t = useStrings().landing;
  return (
    <div className={styles.actions}>
      <div className={styles.buttons}>
        {links.join ? (
          <a href={links.join} className={`btn primary ${styles.big}`} target="_blank" rel="noreferrer">
            <Icon name="chat" size={19} />
            {t.tryIt}
          </a>
        ) : (
          <span className={`btn primary ${styles.big} ${styles.waiting}`} aria-disabled="true" title={t.loading}>
            <Icon name="chat" size={19} />
            {t.tryIt}
          </span>
        )}
        {/* The tour plays by itself, so it never depends on the backend being up. */}
        {example && (
          <Link href="/example" className={styles.example}>
            {t.watch}
            <Icon name="arrow" size={17} />
          </Link>
        )}
      </div>
      {scan && links.join && (
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

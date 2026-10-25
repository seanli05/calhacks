"use client";

import { QRCodeSVG } from "qrcode.react";

import { useStrings } from "@/lib/i18n";

import { TryActions } from "./TryActions";
import type { TryLinks } from "./useTryLinks";
import styles from "./ClosingBand.module.css";

/** QR colors are hex because SVG attributes can't read CSS vars (forest on white). */
const QR_FG = "#0e3b2c";

/**
 * The ask again at the bottom, over the mountain painting: one paper panel with the
 * headline and buttons, and the QR in its own small column for people on a computer.
 */
export function ClosingBand({ links }: { links: TryLinks }) {
  const t = useStrings().landing;
  return (
    <section className={styles.band}>
      <div className={styles.panel}>
        <div className={styles.copy}>
          <h2 className={styles.title}>
            <span>{t.closing.title[0]}</span>{" "}
            <span>
              <span className="mark">{t.closing.title[1]}</span>
            </span>
          </h2>
          <p className={styles.sub}>{t.closing.sub}</p>
          <TryActions links={links} qrSize={0} scan={false} />
        </div>
        {links.join && (
          <div className={styles.scan}>
            <div className={styles.qr}>
              <QRCodeSVG value={links.join} size={104} fgColor={QR_FG} bgColor="#ffffff" level="M" title={t.tryIt} />
            </div>
            <p className={styles.scanLabel}>{t.scan}</p>
          </div>
        )}
      </div>
    </section>
  );
}

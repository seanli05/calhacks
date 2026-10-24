"use client";

import { Icon } from "@/components/Icon";
import { MiniLetter } from "@/components/MiniLetter";
import { stringsFor, useLang } from "@/lib/i18n";

import styles from "./FeatureRows.module.css";

/** Display-only phone numbers, masked like every ref in the dashboard. */
const OFFICIAL_MASKED = "•••-•••-5283";
const PRINTED_MASKED = "•••-•••-0147";
const HELD_FOR = "47:12";

/** Three text + picture rows, one per step, alternating sides. */
export function FeatureRows() {
  const { lang } = useLang();
  const f = stringsFor(lang).landing.features;
  const rows = [
    { copy: f.explain, visual: <ExplainVisual /> },
    { copy: f.verify, visual: <VerifyVisual /> },
    { copy: f.hold, visual: <HoldVisual /> },
  ];
  return (
    <div className={styles.rows}>
      {rows.map(({ copy, visual }, i) => (
        <section key={i} className={`${styles.row} ${i % 2 ? styles.flip : ""}`}>
          <div className={styles.copy}>
            <p className={styles.kicker}>{copy.kicker}</p>
            <h2>{copy.title}</h2>
            <p className={styles.body}>{copy.body}</p>
          </div>
          <div className={styles.visual} aria-hidden="true">
            {visual}
          </div>
        </section>
      ))}
    </div>
  );
}

/** The user's photo, then our answer in their language with the English underneath. */
function ExplainVisual() {
  const { lang } = useLang();
  const t = stringsFor(lang).landing.features.explain;
  const en = stringsFor("en").landing.features.explain;
  return (
    <div className={styles.chat}>
      <div className={styles.photo}>
        <MiniLetter mediaId={null} width={132} />
      </div>
      <div className={styles.reply}>
        <span className="pill">{t.docType}</span>
        <p className={styles.replyText}>{t.bubble}</p>
        {lang !== "en" && <p className={styles.replyEn}>{en.bubble}</p>}
      </div>
    </div>
  );
}

function VerifyVisual() {
  const t = stringsFor(useLang().lang).landing.features.verify;
  return (
    <div className={styles.verify}>
      <span className={`pill ${styles.verdict}`}>
        <Icon name="check" />
        {t.real}
      </span>
      <div className={`${styles.number} ${styles.good}`}>
        <span className={styles.badge}>
          <Icon name="check" size={20} />
        </span>
        <span>
          <span className={styles.numLabel}>{t.official}</span>
          <span className={`mono ${styles.num}`}>{OFFICIAL_MASKED}</span>
        </span>
        <span className={styles.note}>{t.officialNote}</span>
      </div>
      <div className={`${styles.number} ${styles.bad}`}>
        <span className={styles.badge}>
          <Icon name="warn" size={20} />
        </span>
        <span>
          <span className={styles.numLabel}>{t.printed}</span>
          <span className={`mono ${styles.num}`}>{PRINTED_MASKED}</span>
        </span>
        <span className={styles.note}>{t.printedNote}</span>
      </div>
    </div>
  );
}

function HoldVisual() {
  const t = stringsFor(useLang().lang).landing.features.hold;
  return (
    <div className={styles.hold}>
      <div className={styles.waited}>
        <span className="label">{t.waited}</span>
        <span className={styles.bigTime}>{HELD_FOR}</span>
      </div>
      <div className={styles.answered}>
        <span className={styles.ringSmall}>
          <Icon name="phone" size={22} />
        </span>
        <span>
          <strong>{t.answered}</strong>
          <span>{t.ringing}</span>
        </span>
      </div>
    </div>
  );
}

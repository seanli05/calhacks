"use client";

import { Icon } from "@/components/Icon";
import { MiniLetter } from "@/components/MiniLetter";
import { duration } from "@/lib/format";
import { useNow } from "@/lib/api/hooks";
import { stringsFor, useLang, useStrings } from "@/lib/i18n";

import styles from "./BentoVisuals.module.css";

/** Display-only and masked like every ref in the dashboard. */
const OFFICIAL_MASKED = "•••-•••-5283";
/** The hold tile's clock starts here and ticks, so the page feels alive. */
const HOLD_BASE_S = 47 * 60 + 12;
const DAYS_TO_INTERVIEW = 19;

/** The user's photo, our answer in their language (English underneath), and the call offer. */
export function ExplainVisual() {
  const { lang } = useLang();
  const t = stringsFor(lang).landing.bento.explain;
  const en = stringsFor("en").landing.bento.explain;
  return (
    <div className={styles.chat}>
      <div className={styles.photo}>
        <MiniLetter mediaId={null} width={84} />
      </div>
      <div className={styles.bot}>
        <span className="pill">{t.docType}</span>
        <p>{t.bubble}</p>
        {lang !== "en" && <small>{en.bubble}</small>}
      </div>
      <div className={styles.bot}>
        <p>{t.ask}</p>
      </div>
      <div className={styles.me}>{t.yes} ✓</div>
    </div>
  );
}

export function VerifyVisual() {
  const t = useStrings().landing.bento.verify;
  return (
    <div className={styles.panel}>
      <span className={`pill ${styles.verdict}`}>
        <Icon name="check" />
        {t.verdict}
      </span>
      <ul className={styles.checks}>
        {t.checks.map((c) => (
          <li key={c}>
            <span className={styles.tick}>
              <Icon name="check" size={15} />
            </span>
            {c}
          </li>
        ))}
      </ul>
      <div className={styles.official}>
        <Icon name="phone" />
        <span>
          <small>{t.official}</small>
          <span className="mono">{OFFICIAL_MASKED}</span>
        </span>
      </div>
    </div>
  );
}

export function MenuVisual() {
  const t = useStrings().landing.bento.menu;
  return (
    <div className={styles.menuWrap}>
      <p className={styles.prompt}>
        <Icon name="keypad" />
        {t.prompt}
      </p>
      <ol className={styles.menu}>
        {t.options.map((o, i) => (
          <li key={o.key} className={i === t.chosen ? styles.chosen : ""}>
            <span className={styles.key}>{o.key}</span>
            {o.text}
          </li>
        ))}
      </ol>
    </div>
  );
}

export function HoldVisual() {
  const t = useStrings().landing.bento.hold;
  const now = useNow();
  const held = HOLD_BASE_S + (Math.floor(now / 1000) % 600);
  return (
    <div className={styles.hold}>
      <span className={styles.clock}>{duration(held)}</span>
      <span className={styles.holdLabel}>
        <span className={styles.dot} />
        {t.onHold}
      </span>
      <div className={styles.bars}>
        {Array.from({ length: 24 }, (_, i) => (
          <i key={i} style={{ animationDelay: `${(i % 8) * 120}ms` }} />
        ))}
      </div>
    </div>
  );
}

export function RingVisual() {
  const t = useStrings().landing.bento.ring;
  return (
    <div className={styles.ring}>
      <span className={styles.phone}>
        <Icon name="phone" size={30} />
      </span>
      <strong>{t.answered}</strong>
      <span>{t.calling}</span>
    </div>
  );
}

export function PrepVisual() {
  const t = useStrings().landing.bento.prep;
  return (
    <div className={styles.prep}>
      <div className={styles.countdown}>
        <span className={styles.days}>{DAYS_TO_INTERVIEW}</span>
        <span>{t.days}</span>
      </div>
      <div className={styles.prepCols}>
        <ul className={styles.words}>
          {t.words.map((w) => (
            <li key={w.term}>
              <span className="mark">{w.term}</span>
              <small>{w.meaning}</small>
            </li>
          ))}
        </ul>
        <ul className={styles.todo}>
          {t.checklist.map((item, i) => (
            <li key={item} className={i === 0 ? styles.done : ""}>
              <span className={styles.box}>{i === 0 ? "✓" : ""}</span>
              {item}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

export function MemoryVisual() {
  const t = useStrings().landing.bento.memory;
  return (
    <ul className={styles.facts}>
      {t.facts.map((f, i) => (
        <li key={f} className={i === 1 ? styles.gone : ""}>
          <span>“{f}”</span>
          {i === 1 ? (
            <small>{t.deleted}</small>
          ) : (
            <span className={`btn danger ${styles.del}`}>
              <Icon name="trash" size={15} />
              {t.delete}
            </span>
          )}
        </li>
      ))}
      <li className={styles.all}>
        <span className={`btn danger ${styles.del}`}>
          <Icon name="trash" size={15} />
          {t.deleteAll}
        </span>
      </li>
    </ul>
  );
}

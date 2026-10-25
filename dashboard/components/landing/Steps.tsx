"use client";

import { useEffect, useRef, useState } from "react";

import { Icon } from "@/components/Icon";
import { MiniLetter } from "@/components/MiniLetter";
import { useStrings } from "@/lib/i18n";

import styles from "./Steps.module.css";

/** Step 1: a phone sending the letter photo. */
function SendDiagram() {
  return (
    <div className={styles.phone} aria-hidden="true">
      <span className={styles.notch} />
      <div className={styles.sent}>
        <MiniLetter mediaId={null} width={58} />
      </div>
      <span className={styles.sendBtn}>
        <Icon name="arrow" size={14} />
      </span>
    </div>
  );
}

/** Step 2: the letter, read and highlighted, with the check on top. */
function CheckDiagram({ source }: { source: string }) {
  return (
    <div className={styles.checked} aria-hidden="true">
      <MiniLetter mediaId={null} width={92} />
      <span className={styles.seal}>
        <Icon name="check" size={18} />
      </span>
      <span className={styles.source}>{source}</span>
    </div>
  );
}

/** Step 3: office line, on hold, then your phone rings. */
function CallDiagram({ onHold }: { onHold: string }) {
  return (
    <div className={styles.call} aria-hidden="true">
      <span className={styles.node}>
        <Icon name="phone" size={18} />
      </span>
      <span className={styles.wire} />
      <span className={styles.hold}>
        <Icon name="clock" size={13} />
        {onHold}
      </span>
      <span className={styles.wire} />
      <span className={`${styles.node} ${styles.you}`}>
        <Icon name="person" size={18} />
      </span>
    </div>
  );
}

/**
 * How it works. On wide screens the steps scroll past on the left while one window,
 * styled like the hero's chat, stays in view and plays the step in the middle of the
 * screen. On narrow screens each step simply carries its own drawing.
 */
export function Steps() {
  const t = useStrings().landing;
  const [active, setActive] = useState(0);
  const stepRefs = useRef<(HTMLLIElement | null)[]>([]);

  useEffect(() => {
    // A thin band across the middle of the screen: whichever step crosses it is "the" step.
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) setActive(Number((entry.target as HTMLElement).dataset.index));
        }
      },
      { rootMargin: "-45% 0px -45% 0px" },
    );
    stepRefs.current.forEach((el) => el && observer.observe(el));
    return () => observer.disconnect();
  }, []);

  const diagrams = [
    <SendDiagram key="send" />,
    <CheckDiagram key="check" source="uscis.gov" />,
    <CallDiagram key="call" onHold={t.demo.onHold} />,
  ];
  const items = t.steps.items;

  return (
    <section className={styles.band}>
      <header className={styles.head}>
        <h2 className={styles.title}>{t.steps.title}</h2>
        <p className={styles.sub}>{t.steps.sub}</p>
      </header>

      <div className={styles.layout}>
        <ol className={styles.list}>
          {items.map((item, i) => (
            <li
              key={i}
              ref={(el) => {
                stepRefs.current[i] = el;
              }}
              data-index={i}
              className={`${styles.step} ${i === active ? styles.active : ""}`}
            >
              <h3>{item.title}</h3>
              <p>{item.body}</p>
              <div className={styles.inlineArt}>{diagrams[i]}</div>
            </li>
          ))}
        </ol>

        <div className={styles.stage}>
          <figure className={styles.window} aria-hidden="true">
            <div className={styles.bar}>
              <span key={active} className={styles.barTitle}>
                {items[active].title}
              </span>
              <span className={styles.segments}>
                {items.map((_, i) => (
                  <i key={i} className={i <= active ? styles.on : ""} />
                ))}
              </span>
            </div>
            <div className={styles.scenes}>
              {diagrams.map((diagram, i) => (
                <div key={i} className={`${styles.scene} ${i === active ? styles.shown : ""}`}>
                  {diagram}
                  <p className={styles.say}>{t.steps.says[i]}</p>
                </div>
              ))}
            </div>
          </figure>
        </div>
      </div>
    </section>
  );
}

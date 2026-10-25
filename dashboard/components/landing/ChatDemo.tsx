"use client";

import { useEffect, useState } from "react";

import { Icon } from "@/components/Icon";
import { MiniLetter } from "@/components/MiniLetter";
import { useStrings } from "@/lib/i18n";

import styles from "./ChatDemo.module.css";

type Line = "user" | "explain" | "real" | "ask" | "yes" | "calling";

/** The conversation, in order. Bot lines get a typing indicator first. */
const SCRIPT: { line: Line; bot: boolean }[] = [
  { line: "user", bot: false },
  { line: "explain", bot: true },
  { line: "real", bot: true },
  { line: "ask", bot: true },
  { line: "yes", bot: false },
  { line: "calling", bot: true },
];

const TYPING_MS = 1100;
const GAP_MS = 1300;
const RESTART_MS = 5000;

/**
 * The hero visual: the WhatsApp chat a user actually has with us, played on a loop.
 * Scripted, not live data. With reduced motion, the whole chat shows at once.
 */
export function ChatDemo() {
  const t = useStrings().landing.chat;
  const [shown, setShown] = useState(0);
  const [typing, setTyping] = useState(false);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setShown(SCRIPT.length);
      return;
    }
    const timers: ReturnType<typeof setTimeout>[] = [];
    const later = (ms: number, fn: () => void) => timers.push(setTimeout(fn, ms));

    const play = (i: number) => {
      if (i === SCRIPT.length) {
        later(RESTART_MS, () => {
          setShown(0);
          later(600, () => play(0));
        });
        return;
      }
      if (SCRIPT[i].bot) {
        setTyping(true);
        later(TYPING_MS, () => {
          setTyping(false);
          setShown(i + 1);
          later(GAP_MS, () => play(i + 1));
        });
      } else {
        setShown(i + 1);
        later(GAP_MS, () => play(i + 1));
      }
    };
    later(500, () => play(0));
    return () => timers.forEach(clearTimeout);
  }, []);

  const bubble = (line: Line) => {
    switch (line) {
      case "user":
        return (
          <div className={`${styles.msg} ${styles.mine}`}>
            <MiniLetter mediaId={null} width={84} />
            <p>{t.user}</p>
          </div>
        );
      case "real":
        return (
          <div className={`${styles.msg} ${styles.real}`}>
            <span className={styles.badge} aria-hidden="true">
              <Icon name="check" size={15} />
            </span>
            <p>{t.real}</p>
          </div>
        );
      case "yes":
        return <div className={`${styles.reply} ${styles.mine}`}>{t.yes}</div>;
      default:
        return (
          <div className={styles.msg}>
            <p>{t[line]}</p>
          </div>
        );
    }
  };

  return (
    <figure className={styles.phone} aria-label={t.name}>
      <header className={styles.top}>
        {/* eslint-disable-next-line @next/next/no-img-element -- a small avatar; next/image adds nothing here */}
        <img className={styles.avatar} src="/logo.png" alt="" width={40} height={40} />
        <div>
          <p className={styles.name}>{t.name}</p>
          <p className={styles.status}>{typing ? `${t.typing}…` : t.status}</p>
        </div>
      </header>

      <div className={styles.thread} aria-live="off">
        {SCRIPT.slice(0, shown).map(({ line }) => (
          <div key={line} className={styles.enter}>
            {bubble(line)}
          </div>
        ))}
        {typing && (
          <div className={`${styles.msg} ${styles.typing} ${styles.enter}`} aria-label={t.typing}>
            <i />
            <i />
            <i />
          </div>
        )}
      </div>
    </figure>
  );
}

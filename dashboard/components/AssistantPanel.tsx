"use client";

import { useEffect, useRef, useState } from "react";

import { api } from "@/lib/api/client";
import { usePoll } from "@/lib/api/hooks";
import { useLang, useStrings } from "@/lib/i18n";
import { waLink } from "@/lib/whatsapp";

import { Icon } from "./Icon";
import { MiniLetter } from "./MiniLetter";
import styles from "./AssistantPanel.module.css";

/**
 * The right rail on My cases and the case view: three suggestion cards, the
 * WhatsApp thread as the user sees it, and a chat bar. Suggestions and the chat
 * bar open WhatsApp with the text prefilled; the dashboard itself never sends
 * (rules 1 and 5). Replies show up here through polling.
 */
export function AssistantPanel({ userId, className = "" }: { userId: string; className?: string }) {
  const { lang } = useLang();
  const t = useStrings().common.assistant;
  const config = usePoll(() => api.config(), "config", 60_000).data;
  const suggestions = usePoll(() => api.suggestions(userId, lang), `${userId}:${lang}`, 3000).data;
  const messages = usePoll(() => api.messages(userId), userId, 1000).data;
  const [draft, setDraft] = useState("");
  const threadRef = useRef<HTMLDivElement>(null);
  const lastId = messages?.length ? messages[messages.length - 1].id : null;

  useEffect(() => {
    const el = threadRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [lastId]);

  const open = (text: string) => {
    if (!config) return;
    window.open(waLink(config.whatsapp_number, text), "_blank", "noopener");
  };

  return (
    <aside className={`card ${styles.panel} ${className}`} aria-labelledby="assistant-title">
      <div className={styles.head}>
        <div className="label" id="assistant-title">
          {t.title}
        </div>
        <span className={styles.note}>{t.viaWhatsApp}</span>
      </div>

      <div className={styles.sugs}>
        {suggestions?.map((s) => (
          <a
            key={s.id}
            className={styles.sug}
            href={config ? waLink(config.whatsapp_number, s.prefill) : undefined}
            target="_blank"
            rel="noopener noreferrer"
          >
            <span dir="auto">
              <b>{s.title.text}</b>
              <span>{s.detail.text}</span>
            </span>
            <span className={styles.go} dir="auto">
              {s.action.text} <span className="flip-rtl">→</span>
            </span>
          </a>
        ))}
      </div>

      <div className={styles.thread} ref={threadRef}>
        {messages?.map((m) =>
          m.media_ids.length > 0 && !m.body ? (
            <div key={m.id} className={`${styles.msg} ${styles.in} ${styles.photo}`}>
              <MiniLetter mediaId={m.media_ids[0]} />
            </div>
          ) : (
            <div key={m.id} className={`${styles.msg} ${m.direction === "in" ? styles.in : styles.out}`} dir="auto">
              {m.body}
              {m.body_en && m.language !== "en" && m.body_en !== m.body && <small>{m.body_en}</small>}
            </div>
          ),
        )}
      </div>

      <form
        className={styles.composer}
        onSubmit={(e) => {
          e.preventDefault();
          if (!draft.trim()) return;
          open(draft.trim());
          setDraft("");
        }}
      >
        <label htmlFor="assistant-draft" className="visually-hidden">
          {t.placeholder}
        </label>
        <input
          id="assistant-draft"
          autoComplete="off"
          placeholder={t.placeholder}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
        />
        <button type="submit" className={styles.send} aria-label={t.send} title={t.send}>
          <Icon name="arrow" />
        </button>
      </form>
    </aside>
  );
}

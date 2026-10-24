"use client";

import { useState } from "react";

import { FeedList } from "@/components/FeedList";
import { Header } from "@/components/Header";
import { Icon } from "@/components/Icon";
import { MiniLetter } from "@/components/MiniLetter";
import { api, ApiError } from "@/lib/api/client";
import { useFeed, useNow, usePoll } from "@/lib/api/hooks";
import type { Memory } from "@/lib/api/types";
import { relativeTime, shortDate } from "@/lib/format";
import { useLang, useStrings } from "@/lib/i18n";
import { englishBelow } from "@/lib/localized";

import { DeleteEverything } from "./DeleteEverything";
import { FADE_MS, MemoryRow } from "./MemoryRow";
import styles from "./MemoryView.module.css";

const isDeletion = (type: string) => type.endsWith(".deleted") || type === "user.deleted_all";

const isEmpty = (m: Memory) =>
  !Object.keys(m.profile).length && !m.facts.length && !m.documents.length && !m.transcripts.length;

/**
 * Everything we keep about the user, each piece with its own Delete, plus "Delete
 * everything". Deletes only go through the delete routes (rule 5); a deleted row
 * fades out first, then the call is made and the list refetched.
 */
export function MemoryView({ userId }: { userId: string }) {
  const { lang } = useLang();
  const s = useStrings();
  const t = s.memory;
  const now = useNow(15_000);
  const { data: memory, error, refresh } = usePoll(() => api.memory(userId, lang), `${userId}:${lang}`);
  const deletions = useFeed(userId).items.filter((i) => isDeletion(i.type));

  /** Row keys (`fact:<id>`, …) fading out or already deleted. */
  const [leaving, setLeaving] = useState<ReadonlySet<string>>(new Set());
  const [failed, setFailed] = useState<string | null>(null);
  const [wiping, setWiping] = useState(false);
  const [wiped, setWiped] = useState(false);
  const [wipeFailed, setWipeFailed] = useState(false);

  const remove = (key: string, del: () => Promise<unknown>) => {
    setFailed(null);
    setLeaving((prev) => new Set(prev).add(key));
    window.setTimeout(() => {
      del().then(refresh, () => {
        setLeaving((prev) => {
          const next = new Set(prev);
          next.delete(key);
          return next;
        });
        setFailed(key);
      });
    }, FADE_MS);
  };

  const deleteEverything = () => {
    setWipeFailed(false);
    setWiping(true);
    window.setTimeout(() => {
      api.deleteEverything(userId).then(
        () => {
          setWiped(true);
          setWiping(false);
          refresh();
        },
        () => {
          setWiping(false);
          setWipeFailed(true);
        },
      );
    }, FADE_MS);
  };

  const row = (key: string, del: () => Promise<unknown>, content: React.ReactNode) => (
    <MemoryRow key={key} leaving={wiping || leaving.has(key)} failed={failed === key} onDelete={() => remove(key, del)}>
      {content}
    </MemoryRow>
  );

  const notFound = error instanceof ApiError && error.status === 404;

  return (
    <div className={styles.page}>
      <Header userId={userId} />
      <main className={styles.main}>
        <div className={styles.intro}>
          <h1>{t.title}</h1>
          <p>{t.subtitle}</p>
        </div>

        {!memory ? (
          <p className={styles.status}>{notFound ? s.common.notFound : error ? s.common.loadError : s.common.loading}</p>
        ) : isEmpty(memory) ? (
          <p className={`card ${styles.empty}`} role="status">
            {wiped ? t.allDeleted : t.nothingSaved}
          </p>
        ) : (
          <div className={`card ${styles.sheet}`}>
            <section className={`${styles.section} ${wiping ? styles.fading : ""}`} aria-labelledby="mem-profile">
              <h2 className="label" id="mem-profile">
                {t.sections.profile}
              </h2>
              {Object.keys(memory.profile).length ? (
                <dl className={styles.profile}>
                  {Object.entries(memory.profile).map(([k, v]) => (
                    <div key={k}>
                      <dt>{t.profileFields[k] ?? k}</dt>
                      <dd>{v}</dd>
                    </div>
                  ))}
                </dl>
              ) : (
                <p className={styles.none}>{t.empty.profile}</p>
              )}
            </section>

            <section className={styles.section} aria-labelledby="mem-facts">
              <h2 className="label" id="mem-facts">
                {t.sections.facts}
              </h2>
              {memory.facts.length ? (
                <ul className={styles.list}>
                  {memory.facts.map((f) =>
                    row(
                      `fact:${f.id}`,
                      () => api.deleteFact(f.id),
                      <div className={styles.item}>
                        <span className={styles.text}>“{f.fact.text}”</span>
                        {englishBelow(f.fact, lang) && <small className={styles.en}>{f.fact.en}</small>}
                        <span className={styles.meta}>
                          {f.sensitivity === "sensitive" && <span className="pill warn">{t.sensitive}</span>}
                          {f.status === "pending_consent" && <span className="pill warn">{t.pendingConsent}</span>}
                          <span>
                            {t.sources[f.source]} · {t.saved(relativeTime(f.recorded_at, lang, now))}
                          </span>
                        </span>
                      </div>,
                    ),
                  )}
                </ul>
              ) : (
                <p className={styles.none}>{t.empty.facts}</p>
              )}
            </section>

            <section className={styles.section} aria-labelledby="mem-docs">
              <h2 className="label" id="mem-docs">
                {t.sections.documents}
              </h2>
              {memory.documents.length ? (
                <ul className={styles.list}>
                  {memory.documents.map((d) =>
                    row(
                      `doc:${d.id}`,
                      () => api.deleteDocument(d.id),
                      <>
                        <MiniLetter mediaId={d.page_media_ids[0] ?? null} width={52} />
                        <div className={styles.item}>
                          <span className={styles.text}>
                            {(d.doc_type && s.common.docTypes[d.doc_type]) || s.common.docTypeFallback}
                          </span>
                          <span className={styles.meta}>
                            {t.received(relativeTime(d.created_at, lang, now))} · {t.pages(d.page_media_ids.length)}
                          </span>
                        </div>
                      </>,
                    ),
                  )}
                </ul>
              ) : (
                <p className={styles.none}>{t.empty.documents}</p>
              )}
            </section>

            <section className={styles.section} aria-labelledby="mem-calls">
              <h2 className="label" id="mem-calls">
                {t.sections.calls}
              </h2>
              {memory.transcripts.length ? (
                <ul className={styles.list}>
                  {memory.transcripts.map((tr) =>
                    row(
                      `transcript:${tr.id}`,
                      () => api.deleteTranscript(tr.id),
                      <>
                        <span className={styles.icon}>
                          <Icon name="phone" size={20} />
                        </span>
                        <div className={styles.item}>
                          <span className={styles.text}>{t.transcript(shortDate(tr.created_at, lang))}</span>
                          <span className={styles.meta}>{relativeTime(tr.created_at, lang, now)}</span>
                        </div>
                      </>,
                    ),
                  )}
                </ul>
              ) : (
                <p className={styles.none}>{t.empty.calls}</p>
              )}
            </section>
          </div>
        )}

        {memory && !isEmpty(memory) && (
          <>
            {wipeFailed && (
              <p className={styles.failed} role="alert">
                {t.deleteFailed}
              </p>
            )}
            <DeleteEverything busy={wiping} onConfirm={deleteEverything} />
          </>
        )}

        {deletions.length > 0 && (
          <section className={`card ${styles.history}`} aria-labelledby="mem-history">
            <h2 className="label" id="mem-history">
              {t.history}
            </h2>
            <FeedList items={deletions} />
          </section>
        )}
      </main>
      {error && memory && <p className={styles.offline}>{s.common.loadError}</p>}
    </div>
  );
}

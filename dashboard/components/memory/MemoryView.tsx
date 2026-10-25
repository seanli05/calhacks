"use client";

import { useState } from "react";

import { FeedList } from "@/components/FeedList";
import { Header } from "@/components/Header";
import { Icon, type IconName } from "@/components/Icon";
import { MiniLetter } from "@/components/MiniLetter";
import { api, ApiError } from "@/lib/api/client";
import { useFeed, useNow, usePoll } from "@/lib/api/hooks";
import type { Memory } from "@/lib/api/types";
import { relativeTime, shortDate } from "@/lib/format";
import { useLang, useStrings } from "@/lib/i18n";
import { englishBelow } from "@/lib/localized";

import { DeleteEverything } from "./DeleteEverything";
import { FactTag } from "./FactTag";
import { FADE_MS, MemoryRow } from "./MemoryRow";
import styles from "./MemoryView.module.css";

const isDeletion = (type: string) => type.endsWith(".deleted") || type === "user.deleted_all";

const isEmpty = (m: Memory) =>
  !Object.keys(m.profile).length && !m.facts.length && !m.documents.length && !m.transcripts.length;

/** A section's label with its icon, in the left column. */
function SectionHeading({ id, icon, children }: { id: string; icon: IconName; children: React.ReactNode }) {
  return (
    <h2 className={`label ${styles.heading}`} id={id}>
      <span className={styles.headingIcon}>
        <Icon name={icon} size={15} />
      </span>
      {children}
    </h2>
  );
}

/** An empty section: a faint icon tile and a line on what will show up here. */
function EmptySection({ icon, children }: { icon: IconName; children: React.ReactNode }) {
  return (
    <div className={styles.none}>
      <span className={styles.noneIcon}>
        <Icon name={icon} size={18} />
      </span>
      <p>{children}</p>
    </div>
  );
}

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
  const summary =
    memory &&
    [
      memory.facts.length && t.counts.facts(memory.facts.length),
      memory.documents.length && t.counts.documents(memory.documents.length),
      memory.transcripts.length && t.counts.calls(memory.transcripts.length),
    ]
      .filter(Boolean)
      .join(t.separator);

  return (
    <div className={styles.page}>
      <Header userId={userId} />
      <main className={styles.main}>
        <div className={styles.intro}>
          <h1>{t.title}</h1>
          <p>{t.subtitle}</p>
          {summary && <p className={styles.summary}>{summary}</p>}
        </div>

        {!memory ? (
          <p className={styles.status}>{notFound ? s.common.notFound : error ? s.common.loadError : s.common.loading}</p>
        ) : isEmpty(memory) ? (
          <div className={`card ${styles.empty}`} role="status">
            {/* eslint-disable-next-line @next/next/no-img-element -- a small mark; next/image adds nothing here */}
            <img src="/logo.png" alt="" width={56} height={56} />
            <p>{wiped ? t.allDeleted : t.nothingSaved}</p>
          </div>
        ) : (
          <div className={`card ${styles.sheet}`}>
            <section className={`${styles.section} ${wiping ? styles.fading : ""}`} aria-labelledby="mem-profile">
              <SectionHeading id="mem-profile" icon="person">
                {t.sections.profile}
              </SectionHeading>
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
                <EmptySection icon="person">{t.empty.profile}</EmptySection>
              )}
            </section>

            <section className={styles.section} aria-labelledby="mem-facts">
              <SectionHeading id="mem-facts" icon="chat">
                {t.sections.facts}
              </SectionHeading>
              {memory.facts.length ? (
                <ul className={styles.tags}>
                  {memory.facts.map((f) => {
                    const key = `fact:${f.id}`;
                    return (
                      <FactTag
                        key={key}
                        text={f.fact.text}
                        english={englishBelow(f.fact, lang) ? f.fact.en : null}
                        meta={`${t.sources[f.source]}${t.separator}${t.saved(relativeTime(f.recorded_at, lang, now))}`}
                        isPrivate={f.sensitivity === "sensitive"}
                        pending={f.status === "pending_consent"}
                        leaving={wiping || leaving.has(key)}
                        failed={failed === key}
                        onDelete={() => remove(key, () => api.deleteFact(f.id))}
                      />
                    );
                  })}
                </ul>
              ) : (
                <EmptySection icon="chat">{t.empty.facts}</EmptySection>
              )}
            </section>

            <section className={styles.section} aria-labelledby="mem-docs">
              <SectionHeading id="mem-docs" icon="doc">
                {t.sections.documents}
              </SectionHeading>
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
                            {t.received(relativeTime(d.created_at, lang, now))}
                            {t.separator}
                            {t.pages(d.page_media_ids.length)}
                          </span>
                        </div>
                      </>,
                    ),
                  )}
                </ul>
              ) : (
                <EmptySection icon="doc">{t.empty.documents}</EmptySection>
              )}
            </section>

            <section className={styles.section} aria-labelledby="mem-calls">
              <SectionHeading id="mem-calls" icon="phone">
                {t.sections.calls}
              </SectionHeading>
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
                <EmptySection icon="phone">{t.empty.calls}</EmptySection>
              )}
            </section>
          </div>
        )}

        {deletions.length > 0 && (
          <section className={`card ${styles.history}`} aria-labelledby="mem-history">
            <h2 className="label" id="mem-history">
              {t.history}
            </h2>
            <FeedList items={deletions} />
          </section>
        )}

        {memory && !isEmpty(memory) && (
          <section className={styles.privacy} aria-labelledby="mem-privacy">
            <SectionHeading id="mem-privacy" icon="shield">
              {t.privacy.title}
            </SectionHeading>
            <div className={styles.privacyBody}>
              <p>{t.privacy.note}</p>
              {wipeFailed && (
                <p className={styles.failed} role="alert">
                  {t.deleteFailed}
                </p>
              )}
              <DeleteEverything busy={wiping} onConfirm={deleteEverything} />
            </div>
          </section>
        )}
      </main>
      {error && memory && <p className={styles.offline}>{s.common.loadError}</p>}
    </div>
  );
}

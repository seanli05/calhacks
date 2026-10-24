"use client";

import { AssistantPanel } from "@/components/AssistantPanel";
import { FeedList } from "@/components/FeedList";
import { Header } from "@/components/Header";
import { api } from "@/lib/api/client";
import { useFeed, usePoll } from "@/lib/api/hooks";
import { useLang, useStrings } from "@/lib/i18n";

import { CaseCard } from "./CaseCard";
import styles from "./CasesPage.module.css";

/** My cases: active case cards and the user's history | assistant. */
export function CasesPage({ userId }: { userId: string }) {
  const { lang } = useLang();
  const s = useStrings();
  const t = s.cases;
  const { data: cases, error } = usePoll(() => api.cases(userId, lang), `${userId}:${lang}`);
  const { items } = useFeed(userId);

  return (
    <div className={styles.page}>
      <Header userId={userId} />
      <main className={styles.grid}>
        <div className={styles.main}>
          <div className={styles.head}>
            <h1>{t.title}</h1>
            <p>{t.sub}</p>
          </div>

          {!cases ? (
            <p className={styles.status}>{error ? s.common.loadError : s.common.loading}</p>
          ) : cases.length === 0 ? (
            <p className={`card ${styles.empty}`}>{t.empty}</p>
          ) : (
            <ul className={styles.cases}>
              {cases.map((c) => (
                <li key={c.id}>
                  <CaseCard userId={userId} summary={c} />
                </li>
              ))}
            </ul>
          )}

          <section className={`card ${styles.history}`} aria-labelledby="history-title">
            <div className="label" id="history-title">
              {t.history}
            </div>
            {items.length ? (
              <FeedList items={items} className={styles.feed} />
            ) : (
              <p className={styles.status}>{t.historyEmpty}</p>
            )}
          </section>
        </div>
        <AssistantPanel userId={userId} />
      </main>
      {error && cases && <p className={styles.offline}>{s.common.loadError}</p>}
    </div>
  );
}

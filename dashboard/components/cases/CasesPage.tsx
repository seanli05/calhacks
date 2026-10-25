"use client";

import { AssistantPanel } from "@/components/AssistantPanel";
import { Header } from "@/components/Header";
import { api } from "@/lib/api/client";
import { usePoll } from "@/lib/api/hooks";
import { useLang, useStrings } from "@/lib/i18n";

import { CaseCard } from "./CaseCard";
import styles from "./CasesPage.module.css";

/** My cases: one card per active case (each opens the case) | assistant. */
export function CasesPage({ userId }: { userId: string }) {
  const { lang } = useLang();
  const s = useStrings();
  const t = s.cases;
  const { data: cases, error } = usePoll(() => api.cases(userId, lang), `${userId}:${lang}`);

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
        </div>
        <AssistantPanel userId={userId} />
      </main>
      {error && cases && <p className={styles.offline}>{s.common.loadError}</p>}
    </div>
  );
}

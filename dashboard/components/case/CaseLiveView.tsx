"use client";

import { useCallback, useState } from "react";

import { AssistantPanel } from "@/components/AssistantPanel";
import { FeedList } from "@/components/FeedList";
import { Header } from "@/components/Header";
import { api, ApiError } from "@/lib/api/client";
import { useFeed, usePoll } from "@/lib/api/hooks";
import { useLang, useStrings } from "@/lib/i18n";

import { CallHero } from "./CallHero";
import { LetterPanel } from "./LetterPanel";
import { TranscriptSheet } from "./TranscriptSheet";
import styles from "./CaseLiveView.module.css";

/**
 * The screen on camera for the whole call segment of the demo:
 * letter | live call (hero + feed) | assistant.
 */
export function CaseLiveView({ userId, caseId }: { userId: string; caseId: string }) {
  const { lang } = useLang();
  const t = useStrings().common;
  const { data: detail, error } = usePoll(() => api.caseDetail(caseId, lang), `${caseId}:${lang}`);
  const { items } = useFeed(userId);
  const [transcriptCallId, setTranscriptCallId] = useState<string | null>(null);
  const closeTranscript = useCallback(() => setTranscriptCallId(null), []);
  const caseItems = items.filter((i) => i.case_id === caseId);
  const notFound = error instanceof ApiError && error.status === 404;

  return (
    <div className={styles.page}>
      <Header userId={userId} back />
      {!detail ? (
        <p className={styles.status}>{notFound ? t.notFound : error ? t.loadError : t.loading}</p>
      ) : (
        <main className={styles.grid}>
          <LetterPanel detail={detail} />
          <section className={`card ${styles.live}`}>
            <CallHero detail={detail} onOpenTranscript={setTranscriptCallId} />
            <FeedList items={caseItems} className={styles.feed} />
          </section>
          <AssistantPanel userId={userId} />
        </main>
      )}
      {error && detail && <p className={styles.offline}>{t.loadError}</p>}
      {transcriptCallId && <TranscriptSheet callId={transcriptCallId} onClose={closeTranscript} />}
    </div>
  );
}

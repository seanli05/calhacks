"use client";

import { useCallback, useMemo, useState } from "react";

import { AssistantPanel } from "@/components/AssistantPanel";
import { Header } from "@/components/Header";
import { api, ApiError } from "@/lib/api/client";
import { useFeed, useLiveCall, usePoll } from "@/lib/api/hooks";
import type { GlossaryEntry } from "@/lib/api/types";
import { findTerms } from "@/lib/glossary";
import { stringsFor, useLang, useStrings } from "@/lib/i18n";
import { isHumanMoment } from "@/lib/stage";

import { ActivityFeed } from "./ActivityFeed";
import { CallHero } from "./CallHero";
import { GlossaryBook } from "./GlossaryBook";
import { LetterPanel } from "./LetterPanel";
import { LiveTips } from "./LiveTips";
import { LiveTranscript } from "./LiveTranscript";
import { SplitColumn } from "./SplitColumn";
import { TranscriptSheet } from "./TranscriptSheet";
import styles from "./CaseLiveView.module.css";

/**
 * The screen on camera for the whole call segment of the demo:
 * letter | live call (hero + feed) | assistant. Once a person answers, the feed
 * gives way to the live translation, the letter shrinks above the translation book
 * (a resizable split), and the assistant rail gets tips for what to say.
 */
export function CaseLiveView({ userId, caseId }: { userId: string; caseId: string }) {
  const { lang } = useLang();
  const t = useStrings().common;
  const { data: detail, error } = usePoll(() => api.caseDetail(caseId, lang), `${caseId}:${lang}`);
  const { items } = useFeed(userId, true);
  const [transcriptCallId, setTranscriptCallId] = useState<string | null>(null);
  const closeTranscript = useCallback(() => setTranscriptCallId(null), []);
  const caseItems = items.filter((i) => i.case_id === caseId);
  const notFound = error instanceof ApiError && error.status === 404;

  const call = detail?.calls.length ? detail.calls[detail.calls.length - 1] : null;
  // The live layout opens as soon as a person answers, while the user's phone
  // rings to join, not only once they're on.
  const bridged = detail?.stage === "connected" && isHumanMoment(call?.state);
  const live = useLiveCall(call?.id ?? null, bridged);
  const userLang = usePoll(() => api.user(userId), userId, 60_000).data?.language ?? null;
  const glossary = usePoll(() => api.glossary(userLang ?? "en"), `glossary:${userLang}`, 300_000).data ?? [];
  const [query, setQuery] = useState("");
  const [flash, setFlash] = useState<GlossaryEntry | null>(null);
  const pickTerm = useCallback((entry: GlossaryEntry) => {
    setQuery(entry.translation);
    setFlash(entry);
  }, []);
  const seen = useMemo(() => termsUsed(live.lines, glossary, lang), [live.lines, glossary, lang]);

  return (
    <div className={styles.page}>
      <Header userId={userId} back />
      {!detail ? (
        <p className={styles.status}>{notFound ? t.notFound : error ? t.loadError : t.loading}</p>
      ) : (
        <main className={`${styles.grid} ${bridged ? styles.onCall : ""}`}>
          {bridged ? (
            <SplitColumn
              storageKey="dashboard.bookShare"
              label={stringsFor(lang).case.live.resize}
              top={<LetterPanel detail={detail} compact />}
              bottom={
                <GlossaryBook
                  entries={glossary}
                  seen={seen}
                  query={query}
                  flash={flash}
                  onQuery={(q) => {
                    setQuery(q);
                    setFlash(null);
                  }}
                />
              }
            />
          ) : (
            <LetterPanel detail={detail} />
          )}
          <section className={`card ${styles.live}`}>
            <CallHero detail={detail} bridged={bridged} onOpenTranscript={setTranscriptCallId} />
            {bridged ? (
              <LiveTranscript lines={live.lines} glossary={glossary} onTerm={pickTerm} />
            ) : (
              <ActivityFeed items={caseItems} className={styles.feed} />
            )}
          </section>
          {bridged ? (
            <div className={styles.rail}>
              <LiveTips tips={live.tips} />
              <AssistantPanel userId={userId} className={styles.fill} />
            </div>
          ) : (
            <AssistantPanel userId={userId} />
          )}
        </main>
      )}
      {error && detail && <p className={styles.offline}>{t.loadError}</p>}
      {transcriptCallId && <TranscriptSheet callId={transcriptCallId} onClose={closeTranscript} />}
    </div>
  );
}

/** The book entries the call has used so far, most recent first. */
function termsUsed(lines: { text: string }[], glossary: GlossaryEntry[], lang: string): GlossaryEntry[] {
  const side = lang === "en" ? "term" : "translation";
  const seen: GlossaryEntry[] = [];
  for (const line of [...lines].reverse()) {
    for (const seg of findTerms(line.text, glossary, side).reverse()) {
      if (seg.entry && !seen.includes(seg.entry)) seen.push(seg.entry);
    }
  }
  return seen;
}

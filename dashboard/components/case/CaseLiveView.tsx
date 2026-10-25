"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { AssistantPanel } from "@/components/AssistantPanel";
import { Header } from "@/components/Header";
import { Icon } from "@/components/Icon";
import { api, ApiError } from "@/lib/api/client";
import { useFeed, useLiveCall, useNow, usePoll } from "@/lib/api/hooks";
import type { CaseDetail, GlossaryEntry } from "@/lib/api/types";
import { clockTime, daysUntil, intlLocale, longDate } from "@/lib/format";
import { findTerms } from "@/lib/glossary";
import { useLang, useStrings } from "@/lib/i18n";
import { isHumanMoment, isLive } from "@/lib/stage";

import { ActivityFeed } from "./ActivityFeed";
import { CallHero } from "./CallHero";
import { CaseQuestions } from "./CaseQuestions";
import { CaseTabs, isTab, TABS, type Tab } from "./CaseTabs";
import { Drawer } from "./Drawer";
import { GlossaryBook } from "./GlossaryBook";
import { LetterPanel } from "./LetterPanel";
import { LiveTips } from "./LiveTips";
import { LiveTranscript } from "./LiveTranscript";
import { ScamView } from "./ScamView";
import { TodoView } from "./TodoView";
import { TranscriptSheet } from "./TranscriptSheet";
import { VerdictSummary } from "./VerdictSummary";
import { WordsView } from "./WordsView";
import { YourTurn } from "./YourTurn";
import styles from "./CaseLiveView.module.css";

/** How many of the letter's words the overview previews. */
const PEEK_WORDS = 4;

type Panel = "book" | "letter" | "messages";

/**
 * The case page in three tabs (`?tab=`, default the overview). The overview is the
 * focus: the case's current moment over what we've done so far, with the next date,
 * questions to ask and the letter's key words beside it; once a person answers, the
 * live translation, a "your turn" bar and tips take those places. "What to do" is
 * what the letter asks of the family; "Key words" is the translation book. A letter
 * flagged as a scam shows only the warning and its reasons, and has no "What to do".
 * The letter, the book and the WhatsApp thread open in a side drawer. All polling
 * lives here, so switching tabs refetches nothing.
 */
export function CaseLiveView({ userId, caseId }: { userId: string; caseId: string }) {
  const { lang } = useLang();
  const s = useStrings();
  const t = s.common;
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const requested = params.get("tab");
  const select = useCallback(
    (next: Tab) => router.replace(next === "now" ? pathname : `${pathname}?tab=${next}`, { scroll: false }),
    [router, pathname],
  );

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
  const ringing = bridged && call?.state !== "connected";
  const scam = detail?.stage === "suspicious" || detail?.verification?.status === "suspicious";
  const tabs: readonly Tab[] = scam ? ["now", "words"] : TABS;
  const tab: Tab = isTab(requested) && tabs.includes(requested) ? requested : "now";
  const live = useLiveCall(call?.id ?? null, bridged);
  const newest = live.tips[live.tips.length - 1];
  const turn = newest && !newest.used ? newest : null;
  const pastTips = live.tips.filter((tip) => tip !== turn);
  const userLang = usePoll(() => api.user(userId), userId, 60_000).data?.language ?? null;
  const glossary = usePoll(() => api.glossary(userLang ?? "en"), `glossary:${userLang}`, 300_000).data ?? [];
  const [query, setQuery] = useState("");
  const [flash, setFlash] = useState<GlossaryEntry | null>(null);
  const [panel, setPanel] = useState<Panel | null>(null);
  const closePanel = useCallback(() => setPanel(null), []);
  const pickTerm = useCallback((entry: GlossaryEntry) => {
    setQuery(entry.translation);
    setFlash(entry);
    setPanel("book");
  }, []);
  const seen = useMemo(() => termsUsed(live.lines, glossary, lang), [live.lines, glossary, lang]);
  const inLetter = useMemo(() => (detail ? termsInLetter(detail, glossary) : []), [detail, glossary]);
  const onQuery = useCallback((q: string) => {
    setQuery(q);
    setFlash(null);
  }, []);

  // A person answering is the moment that matters: bring the user to the overview once.
  const wasBridged = useRef(bridged);
  useEffect(() => {
    if (bridged && !wasBridged.current && tab !== "now") select("now");
    wasBridged.current = bridged;
  }, [bridged, tab, select]);

  return (
    <div className={`${styles.page} ${tab === "now" ? styles.fixed : ""}`}>
      <Header userId={userId} back />
      {!detail ? (
        <p className={styles.status}>{notFound ? t.notFound : error ? t.loadError : t.loading}</p>
      ) : (
        <>
          <CaseBar detail={detail} />
          <CaseTabs
            tabs={tabs}
            active={tab}
            live={isLive(detail.stage)}
            onSelect={select}
            end={
              <button
                type="button"
                className={styles.messagesButton}
                aria-label={s.case.messages}
                onClick={() => setPanel("messages")}
              >
                <Icon name="chat" size={16} />
                <span>{s.case.messages}</span>
              </button>
            }
          />
          <main id="case-panel" role="tabpanel" aria-labelledby={`tab-${tab}`} className={styles.panel}>
            {tab === "now" && scam && (
              <div className={styles.now}>
                <ScamView detail={detail} />
                <div className={styles.rail}>
                  <CaseQuestions detail={detail} />
                </div>
              </div>
            )}
            {tab === "now" && !scam && (
              <div className={styles.now}>
                <section className={`card ${styles.main}`}>
                  <CallHero detail={detail} bridged={bridged} onOpenTranscript={setTranscriptCallId} />
                  {bridged ? (
                    <>
                      <LiveTranscript
                        lines={live.lines}
                        glossary={glossary}
                        onTerm={pickTerm}
                        turnLineId={turn?.line_id ?? null}
                      />
                      <YourTurn ringing={ringing} tip={turn} />
                    </>
                  ) : (
                    <ActivityFeed items={caseItems} className={styles.feed} />
                  )}
                </section>
                <div className={styles.rail}>
                  {bridged ? (
                    <>
                      <button type="button" className={`btn ${styles.bookButton}`} onClick={() => setPanel("book")}>
                        <Icon name="book" size={16} />
                        {s.case.live.book}
                        <span aria-hidden="true">→</span>
                      </button>
                      {pastTips.length > 0 && <LiveTips tips={pastTips} />}
                    </>
                  ) : (
                    <>
                      {(detail.appointment || detail.deadline) && (
                        <DatePeek detail={detail} onOpen={() => select("todo")} />
                      )}
                      {detail.verification && detail.verification.status !== "verified" && (
                        <VerdictSummary verification={detail.verification} />
                      )}
                      <CaseQuestions detail={detail} />
                      {inLetter.length > 0 && (
                        <WordsPeek entries={inLetter.slice(0, PEEK_WORDS)} onOpen={() => select("words")} />
                      )}
                    </>
                  )}
                </div>
              </div>
            )}
            {tab === "todo" && <TodoView detail={detail} onViewLetter={() => setPanel("letter")} />}
            {tab === "words" && (
              <WordsView entries={glossary} inLetter={inLetter} heard={seen} query={query} onQuery={onQuery} />
            )}
          </main>
        </>
      )}
      {error && detail && <p className={styles.offline}>{t.loadError}</p>}
      {panel === "book" && (
        <Drawer label={s.case.live.book} onClose={closePanel}>
          <GlossaryBook
            entries={glossary}
            seen={seen}
            query={query}
            flash={flash}
            onQuery={onQuery}
            browse={seen.length === 0}
          />
        </Drawer>
      )}
      {panel === "letter" && detail && (
        <Drawer
          label={(detail.doc_type && s.common.docTypes[detail.doc_type]) || s.common.docTypeFallback}
          wide
          onClose={closePanel}
        >
          <LetterPanel detail={detail} />
        </Drawer>
      )}
      {panel === "messages" && (
        <Drawer label={s.case.messages} onClose={closePanel}>
          <AssistantPanel userId={userId} />
        </Drawer>
      )}
      {transcriptCallId && <TranscriptSheet callId={transcriptCallId} onClose={closeTranscript} />}
    </div>
  );
}

/** Which case this is, on every tab: the letter type, who sent it, the appointment. */
function CaseBar({ detail }: { detail: CaseDetail }) {
  const { lang } = useLang();
  const s = useStrings();
  const docType = (detail.doc_type && s.common.docTypes[detail.doc_type]) || s.common.docTypeFallback;
  const status = detail.verification?.status;
  const tone = status === "suspicious" ? "bad" : status === "verified" ? "" : "warn";
  return (
    <div className={styles.caseBar}>
      <span className={styles.docType}>{docType}</span>
      {detail.issuer && <span className={styles.meta}>{detail.issuer}</span>}
      {detail.appointment && <span className={styles.meta}>{longDate(detail.appointment.date, lang)}</span>}
      {status && (
        <span className={`pill ${tone} ${styles.verdictPill}`}>
          {status === "verified" ? "✓ " : ""}
          {s.case.verdict[status]}
        </span>
      )}
    </div>
  );
}

/** The overview's date card: the appointment (or the deadline), how soon, and a way into "What to do". */
function DatePeek({ detail, onOpen }: { detail: CaseDetail; onOpen: () => void }) {
  const { lang } = useLang();
  const t = useStrings().case;
  const now = useNow(60_000);
  const appt = detail.appointment;
  const date = appt?.date ?? detail.deadline!;
  return (
    <button type="button" className={`card ${styles.peek}`} onClick={onOpen}>
      <span className="label">{appt ? t.appt.title : t.todo.deadline}</span>
      <span className={styles.peekDate}>
        {longDate(date, lang)}
        {appt?.time && `, ${clockTime(appt.time, lang)}`}
      </span>
      <span className={styles.peekSub}>
        {new Intl.RelativeTimeFormat(intlLocale(lang), { numeric: "auto" }).format(daysUntil(date, now), "day")}
        {appt?.location && ` · ${appt.location}`}
      </span>
      {detail.checklist.length > 0 && <span className={styles.peekLink}>{t.appt.seeChecklist} →</span>}
    </button>
  );
}

/** The overview's key words card: a few words from the letter, English → the user's language. */
function WordsPeek({ entries, onOpen }: { entries: GlossaryEntry[]; onOpen: () => void }) {
  const t = useStrings().case;
  return (
    <section className={`card ${styles.peek}`}>
      <span className="label">{t.words.inLetter}</span>
      <ul className={styles.peekWords}>
        {entries.map((e) => (
          <li key={e.term}>
            <b>{e.translation}</b>
            <span lang="en">{e.term}</span>
          </li>
        ))}
      </ul>
      <button type="button" className={styles.peekLink} onClick={onOpen}>
        {t.words.seeAll} →
      </button>
    </section>
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

/** The book entries the letter uses, read from its English: explanation, what's asked, checklist. */
function termsInLetter(detail: CaseDetail, glossary: GlossaryEntry[]): GlossaryEntry[] {
  const text = [detail.explanation?.en, detail.what_is_asked?.en, ...detail.checklist.map((c) => c.item.en)]
    .filter(Boolean)
    .join("\n");
  const found: GlossaryEntry[] = [];
  for (const seg of findTerms(text, glossary, "term")) {
    if (seg.entry && !found.includes(seg.entry)) found.push(seg.entry);
  }
  return found;
}

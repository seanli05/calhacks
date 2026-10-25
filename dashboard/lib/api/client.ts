/**
 * The one place pages get data from. By default it calls the FastAPI routes
 * through the `/api` rewrite; `NEXT_PUBLIC_DATA=fixtures` serves `fixtures.ts`
 * instead, so a page can be built without the backend.
 */

import * as fx from "./fixtures";
import * as fxLive from "./fixtures-live";
import type {
  CaseDetail,
  CaseSummary,
  DeleteCounts,
  DemoInfo,
  FeedItem,
  GlossaryEntry,
  LiveCallEvent,
  Memory,
  Message,
  PublicConfig,
  Suggestion,
  Transcript,
  UserInfo,
} from "./types";

export const DATA_MODE: "live" | "fixtures" =
  process.env.NEXT_PUBLIC_DATA === "fixtures" ? "fixtures" : "live";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { cache: "no-store", ...init });
  if (!res.ok) throw new ApiError(res.status, `${init?.method ?? "GET"} ${path} → ${res.status}`);
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

function qs(params: Record<string, string | null | undefined>): string {
  const entries = Object.entries(params).filter((e): e is [string, string] => e[1] != null);
  return entries.length ? `?${new URLSearchParams(entries)}` : "";
}

const fake = <T>(value: () => T): Promise<T> => Promise.resolve().then(value);

const live = {
  demo: () => request<DemoInfo>("/api/demo"),
  config: () => request<PublicConfig>("/api/config"),
  user: (userId: string) => request<UserInfo>(`/api/users/${userId}`),
  feed: (userId: string, since: string | null, lang: string, steps = false) =>
    request<FeedItem[]>(`/api/users/${userId}/feed${qs({ since, lang, steps: steps ? "true" : null })}`),
  cases: (userId: string, lang: string) => request<CaseSummary[]>(`/api/users/${userId}/cases${qs({ lang })}`),
  caseDetail: (caseId: string, lang: string) => request<CaseDetail>(`/api/cases/${caseId}${qs({ lang })}`),
  transcript: (callId: string) => request<Transcript>(`/api/calls/${callId}/transcript`),
  memory: (userId: string, lang: string) => request<Memory>(`/api/users/${userId}/memory${qs({ lang })}`),
  messages: (userId: string) => request<Message[]>(`/api/users/${userId}/messages`),
  suggestions: (userId: string, lang: string) =>
    request<Suggestion[]>(`/api/users/${userId}/suggestions${qs({ lang })}`),
  deleteFact: (factId: string) => request<void>(`/api/facts/${factId}`, { method: "DELETE" }),
  deleteDocument: (documentId: string) => request<void>(`/api/documents/${documentId}`, { method: "DELETE" }),
  deleteTranscript: (transcriptId: string) =>
    request<void>(`/api/transcripts/${transcriptId}`, { method: "DELETE" }),
  deleteEverything: (userId: string) =>
    request<DeleteCounts>(`/api/users/${userId}/delete-everything`, { method: "POST" }),
  glossary: (lang: string) => request<GlossaryEntry[]>(`/api/glossary${qs({ lang })}`),
  /**
   * Streams the bridged call into `emit` (server-sent events); returns stop. After a
   * dropped connection the browser reconnects and the server replays the call from
   * the start, which `useLiveCall` folds into what it already has.
   */
  liveCall: (callId: string, lang: string, emit: (event: LiveCallEvent) => void): (() => void) => {
    const source = new EventSource(`/api/calls/${callId}/live${qs({ lang })}`);
    source.onmessage = (e: MessageEvent<string>) => emit(JSON.parse(e.data) as LiveCallEvent);
    return () => source.close();
  },
};

const fixtures: typeof live = {
  demo: () => fake(fx.demo),
  config: () => fake(fx.config),
  user: (userId) => fake(() => fx.user(userId)),
  feed: (userId, since, lang, steps = false) => fake(() => fx.feed(userId, since, lang, steps)),
  cases: (userId, lang) => fake(() => fx.cases(userId, lang)),
  caseDetail: (caseId, lang) => fake(() => fx.caseDetail(caseId, lang)),
  transcript: (callId) => fake(() => fx.transcript(callId)),
  memory: (userId, lang) => fake(() => fx.memory(userId, lang)),
  messages: (userId) => fake(() => fx.messages(userId)),
  suggestions: (userId, lang) => fake(() => fx.suggestions(userId, lang)),
  deleteFact: (factId) => fake(() => fx.deleteFact(factId)),
  deleteDocument: (documentId) => fake(() => fx.deleteDocument(documentId)),
  deleteTranscript: (transcriptId) => fake(() => fx.deleteTranscript(transcriptId)),
  deleteEverything: (userId) => fake(() => fx.deleteEverything(userId)),
  glossary: (lang) => fake(() => fxLive.glossary(lang)),
  liveCall: fxLive.liveCall,
};

export const api = DATA_MODE === "live" ? live : fixtures;

/** URL for a letter photo or other media (live mode only; fixtures have no bytes). */
export function mediaUrl(mediaId: string): string | null {
  return DATA_MODE === "live" ? `/api/media/${mediaId}` : null;
}

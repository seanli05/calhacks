# Dashboard build guide

Owner: person 1 · For: anyone (human or agent) building a dashboard page · Design: [task-c-dashboard.md → Design](task-c-dashboard.md#design) · API: [dashboard-api.md](dashboard-api.md)

The foundation is built: tokens, i18n, the API types with fake data, shared components, and the live case view. The remaining pages and the API are split so they can be built in parallel without touching the same files.

## Run it

```bash
cd dashboard
npm install
npm run dev            # http://localhost:3000
npm run build          # type-checks every page; must pass before merging
```

Pages run on **live data** by default. With `NEXT_PUBLIC_DATA=fixtures` they use fake data from `lib/api/fixtures.ts` instead, with no backend needed. A **Fixtures** bar at the bottom steps the demo call through its states (◀ ▶ or the arrow keys): waiting for consent → dialing → menu → on hold → person answered → connected → call ended. On a case page it plays that case's call, and each case keeps its own step: the asylum interview starts on hold, the Request for Evidence (`case_demo000000000003`, a deadline instead of an appointment) starts waiting for consent, and the scam letter has no call. Deletes work in fixtures too.

Before that, the feed shows the agents' work live (`ActivityFeed`, grouping in `lib/activity.ts`): each research job or call is a card whose steps (searches, pages read, checks, menus heard; `?steps=true`) stream in under a spinner and shimmering title, then fold behind the result 1.2 s after it finishes ("11 pasos · 0:41 · ver pasos"; the header reopens it). A job that finished with no steps stays plain feed items. Research cards stop spinning after 10 min without news; a call runs until it ends.

The case view has three tabs (`CaseTabs`, kept in `?tab=`). **Overview** shows the hero and tracker over the case's work so far (`ActivityFeed`). Beside it sit the next date (appointment or deadline), the verdict when it isn't verified, two or three questions to ask (`CaseQuestions`, each opens WhatsApp prefilled) and a few of the letter's key words. **What to do** (`TodoView`) adapts to the letter: an appointment (when, where, countdown, map link), a deadline, or just what the letter asks; then a checklist the user can tick (kept in this browser only), what the letter says, and its masked numbers. **Key words** (`WordsView`) is the translation book as cards, on every case. The letter, the translation book and the WhatsApp thread (the Messages button at the end of the tab row) open in a side drawer (`Drawer`). A case bar above the tabs names the letter, sender, appointment and verdict. Overview carries a dot while a call is live.

A letter flagged as a scam (stage `suspicious`) shows only the warning: on My cases the card turns coral with "Likely a scam" and no tracker; on the case view the overview is `ScamView` (the red flags as reasons, what not to do, report links) with scam questions beside it, and there is no What to do tab. Fixtures include one scam case (`case_demo000000000002`).

At **connected** the view jumps to Overview once and switches to the live call: the transcript takes the feed's place, streaming both sides word by word in the viewer's language (`LiveTranscript`), a "Your turn" bar under it (`YourTurn`) says when the user is needed (pick up the phone, answer this yourself, or a question to ask) and marks the line that prompted it, and earlier tips take the side cards' place (`LiveTips`), and the hero shrinks to a bar after 3 s ("Details" reopens it). The translation book opens in the drawer from its button or by tapping an underlined word. Fixtures play a scripted call (`lib/api/fixtures-live.ts`); live mode reads `GET /api/calls/{call_id}/live` and `GET /api/glossary` ([dashboard-api.md → Live call](dashboard-api.md#live-call)). On a real call, lines appear only once the phone agent saves the transcript as it goes, not only at wrap-up.

With the backend running, `npm run dev` calls the real API through the `/api` rewrite (`BACKEND_URL`, default `http://localhost:8000`; see `.env.example`).

Useful URLs on fixtures: `/u/user_demo000000000001` (My cases), `/u/user_demo000000000001/cases/case_demo000000000001` (case view), `/u/user_demo000000000001/memory`.

## Layout

```
dashboard/
  app/
    layout.tsx                 fonts, LanguageProvider, FixtureBar
    globals.css                design tokens + shared primitives
    page.tsx                   landing                      → landing agent
    u/[userId]/layout.tsx      UserShell (user's language)
    u/[userId]/page.tsx        My cases                     → my-cases agent
    u/[userId]/memory/page.tsx What we know about you       → memory agent
    u/[userId]/cases/[caseId]/page.tsx   live case view (built)
  components/                  shared: Header, Tracker, FeedList, AssistantPanel, MiniLetter, Icon, FixtureBar
    case/                      case view: CaseLiveView (tabs), CaseTabs, Drawer, CallHero, TodoView, WordsView, ScamView, CaseQuestions, YourTurn, LetterPanel, VerdictSummary, ActivityFeed, GlossaryBook, LiveTranscript, LiveTips, TranscriptSheet
    landing/ cases/ memory/    one folder per page agent (create yours)
  lib/
    api/types.ts               the API contract (mirrored by backend/app/api/models.py)
    api/fixtures.ts            fake data + the demo-call stepper
    api/client.ts              `api.*`: live or fixtures
    api/hooks.ts               usePoll, useFeed, useNow
    i18n/                      LanguageProvider, useStrings, strings/<lang>/<page>.ts
    format.ts                  relative times, dates, durations (Intl, any language)
    stage.ts                   case stage → tracker step, live, warning
    whatsapp.ts                wa.me links
```

## Conventions

- **Look.** Use the tokens in `globals.css` (`--forest`, `--lime`, `--fs-*`, …) and the shared classes (`card`, `label`, `pill`, `btn`, `btn primary`, `btn danger`, `mark`, `pin`, `mono`). Corners are square, borders hairline, no shadows on cards. Bright green (`--lime`) is a highlighter fill or a small accent, never a glow. Status: amber for warnings, coral for "suspicious". Check the live case view before inventing anything new.
- **Legible on video.** The demo is recorded at 1080p. Body text is `--fs-md` (15px), feed and key text `--fs-lg`, nothing under 12px, and relative times only ("3 min ago"), no clock timestamps.
- **Styles** live in a CSS module next to the component. No Tailwind, no component library.
- **Strings.** No hard-coded user-facing text in components. Put it in `lib/i18n/strings/en/<page>.ts` and mirror it in `strings/es/<page>.ts` and `strings/fa/<page>.ts` (Dari; the type forces every key). Dari is right to left: use logical CSS properties (`margin-inline-start`, `inset-inline-end`), not `left`/`right`, and format dates through `lib/format.ts`. Read it with `useStrings().<page>`. Text that comes from data (`Localized`) shows `.text`, with `.en` muted underneath when the UI isn't in English.
- **Data.** Only through `api.*` and the hooks in `lib/api/hooks.ts`. Poll about once a second (`usePoll`). Never call `fetch` directly.
- **Rules from CLAUDE.md that touch the UI.** The dashboard never sends WhatsApp messages: it only opens `wa.me` links with text prefilled (rule 1). It only deletes through the delete routes, never writes anything else (rule 5). Sensitive refs arrive masked; never unmask or log them.
- **Dependencies.** Already installed and pinned: `next`, `react`, `qrcode.react` (for the landing QR). Don't add others without asking person 1.
- **Shared files.** Don't edit `lib/api/types.ts`, `globals.css`, `lib/i18n/index.tsx` or the shared components without telling person 1. If you need a new shared token or component, ask. Each page agent owns only its own route, its `components/<page>/` folder, and its two strings files.

## Git

- Your own worktree and branch: `git worktree add ../calhacks26-<topic> -b chris/<topic> main`, then `cd ../calhacks26-<topic>/dashboard && npm install`.
- Small commits, one short imperative line, no AI attribution.
- Before merging: `git pull` (or `git merge main`), `npm run build` passes, then fast-forward `main` to your branch. For backend work also `ruff format . && ruff check --fix . && pytest` from the repo root.

## Work split

| Agent | Builds | Owns | Done when |
|---|---|---|---|
| **API** | Task C step 2: every route in [dashboard-api.md](dashboard-api.md), feed and suggestion templates, new reads, seed, settings, tests | `backend/app/api/`, `backend/app/main.py` (mount only), `backend/app/db/reads.py` (new reads only), `backend/app/db/reset.py` (seed only), `backend/app/settings.py` + `.env.example` (one setting), `backend/tests/test_api_*.py` | Every route returns the `types.ts` shape on the seeded DB; tests pass; the case view works with `NEXT_PUBLIC_DATA=live` |
| **Landing** | `/`: headline, three steps, QR that opens WhatsApp with the sandbox join message (`api.config()`), link to the live dashboard (`api.demo()`) | `app/page.tsx`, `components/landing/`, `strings/*/landing.ts` | Looks right at 1080p and on a phone; QR scans to the right `wa.me` link |
| **My cases** | `/u/[userId]`: case cards (doc type, stage pill, tracker, hold timer when on hold, appointment) and AssistantPanel on the right; no history list (the case view shows each case's activity). Cards link to the case view | `app/u/[userId]/page.tsx`, `components/cases/`, `strings/*/cases.ts` | Works through every fixture step; empty state when there are no cases |
| **Memory** | `/u/[userId]/memory`: profile, facts (sensitive ones marked), documents, transcripts, each with Delete; "Delete everything" with an in-page confirm (no `confirm()`); deleted rows fade out | `app/u/[userId]/memory/page.tsx`, `components/memory/`, `strings/*/memory.ts` | Every delete works on fixtures and shows "(deleted …)" in the case view's feed |

After the API lands, one pass wires it together: run everything with `NEXT_PUBLIC_DATA=live` on the seeded database at 1920×1080, fix mismatches, make `live` the default in `lib/api/client.ts`, and write the deployment steps (task C step 5).

## Start prompts

Paste one into a fresh Claude Code session at the repo root.

**API**
> You're building the dashboard API (task C step 2). Read `backend/AGENTS.md`, then `docs/specs/dashboard-api.md` (your spec), then `dashboard/lib/api/types.ts` and `dashboard/lib/api/fixtures.ts` (the response contract and example values). Work in your own worktree: `git worktree add ../calhacks26-api -b chris/dashboard-api main`. Stay inside the files the spec's work split gives you; ask before changing contracts, the schema, or anyone else's package. Don't run `app.db.reset` against the shared database: use `TEST_DATABASE_URL`. Commit after each route group, run `ruff format . && ruff check --fix . && pytest`, and fast-forward `main` when green. When done, report which event `data` fields the feed templates expect, so the team can emit them.

**Landing**
> You're building the dashboard's landing page. Read `docs/specs/dashboard-build.md` (conventions, your row in the work split), then the Design section of `docs/specs/task-c-dashboard.md`, then look at `components/case/` for how the existing page uses tokens, strings and `api.*`. Work in your own worktree: `git worktree add ../calhacks26-landing -b chris/dashboard-landing main`. Only edit the files your row owns. Run on fixtures (`npm run dev` in `dashboard/`). Commit often, `npm run build` must pass, then fast-forward `main`.

**My cases**
> You're building the dashboard's My cases page (`/u/[userId]`). Read `docs/specs/dashboard-build.md` (conventions, your row in the work split), then the Design section of `docs/specs/task-c-dashboard.md`, then `components/case/` and `components/AssistantPanel.tsx`, which you'll reuse. Work in your own worktree: `git worktree add ../calhacks26-cases -b chris/dashboard-cases main`. Only edit the files your row owns. Run on fixtures (`npm run dev` in `dashboard/`) and step through the whole call with the Fixtures bar. Commit often, `npm run build` must pass, then fast-forward `main`.

**Memory**
> You're building the dashboard's "What we know about you" page (`/u/[userId]/memory`). Read `docs/specs/dashboard-build.md` (conventions, your row in the work split), then the Design section of `docs/specs/task-c-dashboard.md`, then `components/case/` for how the existing page uses tokens, strings and `api.*`. Work in your own worktree: `git worktree add ../calhacks26-memory -b chris/dashboard-memory main`. Only edit the files your row owns. Deletes go through `api.deleteFact` and friends; the confirm for "Delete everything" is built into the page (browser `confirm()` is not allowed). Run on fixtures (`npm run dev` in `dashboard/`). Commit often, `npm run build` must pass, then fast-forward `main`.

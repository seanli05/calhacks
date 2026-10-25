# Saving the transcript live during the bridge

**For:** Sean (phone agent) · **From:** Chris · **Branch:** `chris/phone-live-transcript`

## Why

The case view now has a live call screen. Once the user is bridged, both sides of the call show up line by line in the user's language, with the translation streaming in word by word, tips for what to say, and a searchable translation book. The dashboard API reads it from the call's `transcripts` row ([dashboard-api.md → Live call](specs/dashboard-api.md#live-call)).

Today the runner writes that row once, at wrap-up (`runner.py`, `_wrap_up`). During the call the row doesn't exist, so the live screen stays empty.

## What I'd like changed

Save the transcript in the background each time a line is added while the call is `bridging` or `connected`. `writes.phone.save_transcript` already creates or replaces the row and says it's safe to call as the call goes on, so no schema or contract change is needed.

The branch has a version of this for you to review, change or replace:

- **`runner_base.py`**
  - `_said` calls `_save_transcript_soon()` when the state is `bridging` or `connected`.
  - That starts a background task that saves a copy of the transcript through `deps.calls.save_transcript`, with `cleanup_timeout_s` as the timeout.
  - One save runs at a time. Lines that arrive during a save go into the next one, so a burst of lines makes at most two saves.
  - A failed save is logged with the call's ids and dropped. Only the live view misses out; the call carries on.
- **`runner.py`**
  - `_wrap_up` lets any live save finish before the final save, so an older copy can't land after the full transcript.
  - `_stop_tasks` cancels a live save that's still running.
  - The final save and the report are unchanged.
- **`tests/test_phone_runner.py`**
  - One new test: during a bridged call, a save before the end already holds the first overheard line, and the last save is the whole transcript.
  - It fails without the change.

## What it doesn't change

- No change to what goes into the transcript, the state machine, events, ports or fakes.
- Before the bridge nothing new happens: menu and hold lines are still saved once, at wrap-up.
- The dashboard only shows `agency` and `user` lines from the `call.user_joined` event on.

## Checks

- `pytest tests/test_phone_runner.py`: 38 passed.
- All phone tests: 434 passed and 1 failed. The failure is `test_phone_call_lines.py::test_every_language_users_write_in_has_a_join_prompt[fa]`, which fails on `main` too: there's no Farsi join prompt.

## Questions for you

1. Is a database write per heard line during the bridge fine, given how the runner uses the event loop? Each one is a single small upsert, and saves never overlap.
2. Would you rather save from `_dispatch`'s `Overheard` case only, instead of from `_said`?

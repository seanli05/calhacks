# Demo reset: review before running on the host

**For:** Sean (host), Lauren, Rakshan. **Branch:** `chris/mariam-seed`. Nothing here has been run on the host yet.

One command puts the host database back to the demo's starting state between takes, in a few seconds, without touching anyone's account.

## The command

Run from `backend/` on the host, with no call or research in progress:

```
python -m app.db.reset --yes --keep-users \
  --demo-user user_e2349da15dde9b4b=mariam \
  --demo-user user_7c30cc862fd031a0=ana \
  --with-scam
```

Leave out `--with-scam` when the scam letter is sent live on camera.

## What it does

1. Checks both accounts exist. If one is missing, it stops before changing anything.
2. Empties every table except `users` and `glossary` (one `TRUNCATE`). Every account keeps its ID, WhatsApp number and creation date, including accounts not in the demo.
3. Sets each demo account's language from its persona: Lauren's account becomes Dari (`fa`, it's `es` today), Sean's stays English.
4. Seeds the same story on both accounts, each in its own language:

| | Lauren's account (`mariam`) | Sean's account (`ana`) |
|---|---|---|
| Name in the profile | Mariam Namuna | Ana Morales |
| Language | Dari | English |
| Medi-Cal renewal (MC 216, Alameda County) | Explained, verified, chat finished with nothing left open | Same, in English |
| Sensitive fact waiting for OK | "Has Medi-Cal health coverage" | Same |
| Scam letter, with `--with-scam` | Fake ICE AR-11 notice, flagged suspicious, 4 red flags; told not to pay | Same, letter in Ana's name |
| I-797C | Not seeded: sent live on camera | Not seeded |

5. Refreshes the translation book (257 terms).

Bookmarked "My cases" links keep working, since user IDs never change. Case IDs do change, so open cases from My cases.

## What to check

- **Lauren:** the Dari WhatsApp text in `backend/app/db/seed_mariam.py` (Medi-Cal and scam chats), and that a seeded sensitive fact waiting for OK doesn't make the orchestrator bring it up mid-demo. Also note the new `verified` stage below.
- **Sean:** the account IDs above are the ones you sent; run it only when the host is idle. If anything looks stuck afterwards, restart the backend.
- **Everyone:** the scam letter (`demo/letters/scam_ar11_*.png`) and the Medi-Cal story read right.

## Other changes on this branch

- **New case stage `verified`.** Since letters no longer get a call offer by default, a verified letter now shows "This letter is real" instead of "Should we call…? Reply YES". `awaiting_consent` now means a call was actually offered (`consent.requested` or `consent.given`, not declined). `get_case_status` reports `verified` for these cases; one line of `test_orchestrator_turn.py` was updated to match.
- **Live call view opens when a person answers**, not only once the user has joined.
- **Reset loads the glossary in one statement**, so a full reset takes about 11 s instead of ~2 min.

## Full reset (only after a schema change)

`--keep-users` keeps the tables as they are. If someone changes the schema, run the same command without `--keep-users` once: it drops and rebuilds every table, then recreates both accounts with the same IDs and numbers.

## Not yet tested

The database tests for `--keep-users` and the kept accounts (`backend/tests/test_db_helpers.py`) haven't been run; the pure tests pass. Run `pytest backend/tests/test_db_helpers.py` against the test branch before the first host run.

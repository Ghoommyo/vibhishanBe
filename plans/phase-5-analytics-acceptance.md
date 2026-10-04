# Phase 5: Analytics, acceptance, deploy readiness (endpoint 26)

## Goal
The provider dashboard stats, an end-to-end run of the spec §11 checklist, and a project ready to deploy on Vercel.

## Steps
1. Add `app/schemas/analytics.py` (`ProviderStats`) and `app/services/analytics.py`:
   - `listeningDone`, `moderationDone` and `activeSessions` from the caller's rooms
   - rating average, count and 1–5 distribution
   - 8 weekly buckets (oldest first, `start < closedAt <= end`). The label is "Now" for the last bucket, otherwise `d/m` of `start + 1ms` shifted by `-tzOffset` minutes.
   - feedback that has non-empty text, newest first, with `by`
2. Add `app/routers/analytics.py` (`GET /analytics/provider?tzOffset=`).
3. Add `tests/test_acceptance.py`, which runs §11 steps 1–13 in order against a freshly seeded database.
4. Generate `requirements.txt` with `uv export --no-dev --no-hashes`. Add a `README.md` covering setup, migrations, seeding, running, tests and the Vercel deploy and env vars. Update the commands in `CLAUDE.md`.

## Tests
- Seed analytics for Lisa: listeningDone 3, activeSessions 1, average 4.67, and the distribution. A plain user gets zeros, and the weekly labels respect `tzOffset`.
- The full acceptance flow passes.

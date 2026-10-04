# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

This is the backend for **Vibishan**, a React Native (Expo) app that connects users with listeners and moderators. All 28 endpoints in [backend-api-spec.md](backend-api-spec.md) are implemented. The phased build plans are in [plans/](plans/).

**`backend-api-spec.md` is the source of truth.** It is the contract the mobile app already codes against (through an in-app mock backend). Endpoint paths, JSON shapes, validation order, error codes, and **user-facing error and notification message strings must match the spec exactly**, so the app can switch from the mock without UI changes. Read the relevant spec section before implementing or changing any endpoint.

## Stack and commands

FastAPI, Pydantic v2, SQLAlchemy 2.x (sync), Alembic, `psycopg[binary]` v3, PyJWT (HS256) and `argon2-cffi` (used directly instead of passlib), on PostgreSQL, deployed to Vercel's Python runtime. Dependencies are managed with **uv** (Python 3.12) in `pyproject.toml` and `uv.lock`. `requirements.txt` is generated for Vercel, so regenerate it after any dependency change with `uv export --no-dev --no-hashes --no-emit-project -o requirements.txt`.

- `uv run pytest`: run the full suite. For a single test, use `uv run pytest tests/test_rooms.py::test_mute_unmute`.
- `uv run alembic upgrade head`: apply migrations. Run this from a dev machine or CI, never at app startup. Create new revisions with `uv run alembic revision --autogenerate -m "..."` and review the output.
- `uv run python -m app.seed`: truncate the tables and load the spec §9 seed. Every seed password is `password123`.
- `uv run uvicorn app.main:app --reload`: start the local dev server.

Local Postgres is Postgres.app, and its binaries (`psql`, `createdb`) are in `/Applications/Postgres.app/Contents/Versions/latest/bin`, which isn't on `PATH`. Dev uses the `vibishan` database and tests use `vibishan_test`.

Env vars: `DATABASE_URL`, `JWT_SECRET`, `JWT_EXPIRES_DAYS`, `CORS_ORIGINS`, `ENABLE_DEV_ENDPOINTS` (see `.env.example`). Tests also read `TEST_DATABASE_URL`.

## Testing

`tests/conftest.py` overrides `DATABASE_URL` with the test database before the app is imported, runs the migrations once, and **truncates and re-seeds before every test**, so tests can rely on the exact seed state. The `auth("alice")` fixture returns bearer headers for a seed user, and the `db` fixture is a raw session. If a test holds `db` while calling an endpoint that truncates (`/dev/reset`), call `db.rollback()` first or the TRUNCATE will block. `tests/test_acceptance.py` is the spec §11 checklist.

## Architecture (spec §10 layout)

- `api/index.py` — Vercel entry; just `from app.main import app`. `vercel.json` rewrites all paths to `/api/index`.
- `app/main.py` — FastAPI app, CORS, error handlers, all routers mounted under `/api/v1`.
- `app/core/` — config (pydantic-settings), security (password hashing, JWT, `get_current_user` dependency), errors (`ApiError(code, message)` + code→HTTP status map).
- `app/db/`: engine and session (`get_db` commits or rolls back once per request) plus the models for the normalized schema in spec §8. The models have no ORM relationships, so related rows are loaded in bulk by hand. Flush a parent row before adding rows that reference it by foreign key.
- `app/schemas/` — camelCase Pydantic models for spec §5.
- `app/services/`: **all business rules (spec §7) live here**, and routers stay thin. Services take `(db, caller, ...)`, raise `ApiError` and return Pydantic schemas. Shared serializers: `users.public_user` / `load_users`, `requests_common.serialize_requests`, `rooms.build_rooms` / `build_messages`.
- `app/routers/` — HTTP layer only.

## Constraints that shape every change

- **Serverless/stateless (Vercel):** no in-memory caches, background tasks, schedulers or WebSockets — the client polls. Keep imports light. Engine uses `NullPool` (or `pool_size=1, max_overflow=0, pool_pre_ping=True`) with the provider's *pooled* connection string; don't connect at import time.
- **Wire format:** camelCase via `alias_generator=to_camel, populate_by_name=True`. Timestamps are **integer epoch milliseconds** on the wire and `timestamptz` in the DB. Always use `app.core.utils.now()`, which truncates to milliseconds so `?after=` polling round-trips exactly, and convert with `to_ms` / `from_ms`. Nullable fields are returned as `null`, never omitted.
- **IDs:** opaque `text` keys, generated as `<prefix>_<random>` with prefixes `u_`, `req_`, `room_`, `msg_`, `ntf_`. Seed data uses readable ids (`u_alice`, `room_seed1`).
- **Errors:** every error is `{"error": {"code", "message"}}`; FastAPI's `RequestValidationError` must also be mapped to `422` / `validation` in this envelope.
- **Nested shapes are assembled from normalized tables:** `approvals`, `participantIds`, `memberIds` (ordered by `position`: requester, participants…, provider), `mutedIds`, `closures` (dict by user id), `ratings`, `starredBy`. Avoid N+1 on `/rooms`, `/notifications`, `/rooms/{id}/messages` — bulk-load related rows and cache users per request.
- **Transactions:** each mutating endpoint is one transaction; `respond`, closure submission, rating and mute must lock the request/room row with `SELECT … FOR UPDATE`.
- **Room access:** a room that doesn't exist *or* that the caller isn't a member of returns `404 "Chatroom not found."` (never 403).

## Core domain logic to get right (spec §7)

- Creating a request always creates its room in `pending` status. The requester is **not** in `approvals`.
- Moderated sessions: every participant must accept before the moderator may respond; the moderator is only notified once all participants have accepted. Any rejection rejects request and room.
- `sendBlockedReason` precedence: pending → rejected → closed → already submitted closure → muted.
- Closing: the room closes immediately on the moderator's verdict; a listen room closes only when every member has submitted. A moderated room never closes from member closures alone.
- Only `member`s rate, once, after close. `notify()` creates `request_update` notifications pre-read when the recipient has `notifyRequests = false`.
- Display name = `profile.name` if non-empty, else `username`. Participant lists are formatted "A", "A and B", "A, B and C" (no Oxford comma).

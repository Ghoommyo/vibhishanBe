# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

This is the backend for **Vibishan**, a React Native (Expo) app that connects users with listeners and moderators. The repo currently contains only `pyproject.toml` (no dependencies yet) and [backend-api-spec.md](backend-api-spec.md). No application code exists yet.

**`backend-api-spec.md` is the source of truth.** It is the contract the mobile app already codes against (via an in-app mock backend). Endpoint paths, JSON shapes, validation order, error codes and **user-facing error/notification message strings must match the spec exactly**, so the app can switch from the mock without UI changes. Read the relevant spec section before implementing or changing any endpoint.

## Stack and intended commands

FastAPI + Pydantic v2 + SQLAlchemy 2.x + Alembic + `psycopg[binary]` v3 + PyJWT (HS256) + passlib/argon2, on PostgreSQL (Neon/Supabase), deployed to Vercel's Python runtime. Dependencies go in `requirements.txt` (pinned), which is what Vercel installs (spec §10).

Commands the spec defines (once the code exists):
- `alembic upgrade head` — run migrations (from dev machine/CI only, never at app startup)
- `python -m app.seed` — load seed data (spec §9)
- `pytest` / `pytest tests/test_x.py::test_name` — tests use httpx `TestClient` against a test Postgres
- `uvicorn app.main:app --reload` — local dev server

Env vars: `DATABASE_URL`, `JWT_SECRET`, `JWT_EXPIRES_DAYS`, `CORS_ORIGINS`, `ENABLE_DEV_ENDPOINTS` (see spec §3.6; provide a `.env.example`).

## Architecture (spec §10 layout)

- `api/index.py` — Vercel entry; just `from app.main import app`. `vercel.json` rewrites all paths to `/api/index`.
- `app/main.py` — FastAPI app, CORS, error handlers, all routers mounted under `/api/v1`.
- `app/core/` — config (pydantic-settings), security (password hashing, JWT, `get_current_user` dependency), errors (`ApiError(code, message)` + code→HTTP status map).
- `app/db/` — engine/session and SQLAlchemy models for the normalized schema in spec §8.
- `app/schemas/` — camelCase Pydantic models for spec §5.
- `app/services/` — **all business rules (spec §7) live here**; routers stay thin.
- `app/routers/` — HTTP layer only.

## Constraints that shape every change

- **Serverless/stateless (Vercel):** no in-memory caches, background tasks, schedulers or WebSockets — the client polls. Keep imports light. Engine uses `NullPool` (or `pool_size=1, max_overflow=0, pool_pre_ping=True`) with the provider's *pooled* connection string; don't connect at import time.
- **Wire format:** camelCase via `alias_generator=to_camel, populate_by_name=True`. Timestamps are **integer epoch milliseconds** on the wire, `timestamptz` in the DB. Nullable fields are returned as `null`, never omitted.
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

Spec §11 is an end-to-end acceptance checklist against a freshly seeded DB; use it to verify behaviour.

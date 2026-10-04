# Vibishan backend: build plans

The backend implements the contract in [`../backend-api-spec.md`](../backend-api-spec.md), which is the source of truth for every endpoint, message string and business rule. It is built in phases. Each phase ends with passing tests and a commit pushed to `main`.

| Phase | Plan | Scope | Endpoints (spec §6.0 #) |
|---|---|---|---|
| 0 | [phase-0-scaffolding.md](phase-0-scaffolding.md) | Project setup, config, error envelope, DB session, health | 28 |
| 1 | [phase-1-database.md](phase-1-database.md) | SQLAlchemy models, Alembic migration, seed data, dev reset | 27 |
| 2 | [phase-2-auth-users.md](phase-2-auth-users.md) | JWT auth, signup and login, profiles, settings, provider and user search | 1–10 |
| 3 | [phase-3-requests-notifications.md](phase-3-requests-notifications.md) | Listen and moderate requests, approval state machine, notifications | 11–13, 23–25 |
| 4 | [phase-4-rooms-chat.md](phase-4-rooms-chat.md) | Chatrooms, messages, stars, closures, mute, ratings, summary | 14–22 |
| 5 | [phase-5-analytics-acceptance.md](phase-5-analytics-acceptance.md) | Provider analytics, §11 acceptance test, deploy readiness | 26 |

## Decisions that apply to every phase
- **Toolchain:** uv with Python 3.12. `requirements.txt`, which Vercel installs, is generated with `uv export --no-dev --no-hashes`.
- **Database:** local Postgres (Postgres.app 17). The `vibishan` database is for development and `vibishan_test` is for pytest.
- **Password hashing:** `argon2-cffi` directly. passlib is unmaintained, and this choice doesn't affect the API.
- **Sync SQLAlchemy 2 with `NullPool`:** this suits Vercel's serverless runtime. Each request runs in one transaction, committed by the `get_db` dependency.
- **Thin routers.** All business rules live in `app/services/`.
- **Tests:** every test starts from a freshly re-seeded database (truncate, then `app.seed.seed()`).

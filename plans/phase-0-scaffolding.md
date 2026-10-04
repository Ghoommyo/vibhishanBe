# Phase 0: Scaffolding

## Goal
A runnable FastAPI app with config, the spec's error envelope, a database session and `GET /api/v1/health`, ready to deploy on Vercel.

## Steps
1. Pin Python with `uv python pin 3.12`. `pyproject.toml` declares the runtime and dev dependencies and the pytest config.
2. Add `.gitignore`, `.env.example` with the env vars from spec §3.6, `vercel.json` (rewriting everything to `/api/index`), and `api/index.py`, which re-exports `app`.
3. Add the core modules:
   - `app/core/config.py`: pydantic-settings that read `.env`. `CORS_ORIGINS` is parsed from a comma-separated list.
   - `app/core/errors.py`: `ApiError(code, message)`, the code→HTTP status map, and handlers for `ApiError`, `RequestValidationError` (returns 422 `validation`) and Starlette `HTTPException`, so 404 and 405 use the envelope too.
   - `app/core/utils.py`: `now()`, `to_ms`/`from_ms`, `new_id(prefix)`, `display_name`, `join_names`.
4. Add `app/db/session.py`: a lazily created engine with `NullPool`, a `SessionLocal`, and a `get_db` dependency that commits on success and rolls back on error.
5. Add `app/main.py` (the app, CORS, handlers, and routers under `/api/v1`) and `app/routers/health.py` (`SELECT 1`, returns 503 when the DB is down).
6. Create the `vibishan` and `vibishan_test` databases.

## Tests
- `GET /api/v1/health` returns `{"status": "ok"}`.
- An unknown path returns 404 with `{"error": {"code": "not_found", ...}}`.
- `join_names` formats lists as "A", "A and B" and "A, B and C".

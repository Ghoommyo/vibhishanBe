# Vibishan API

The REST backend for the Vibishan app. Users request 1:1 listening sessions with listeners, or moderated group sessions with moderators, and then chat, close out and rate the session.

It is built with FastAPI, SQLAlchemy 2, Alembic and PostgreSQL, and deploys to Vercel's Python runtime.

The API contract (endpoints, payloads, error messages and business rules) is in [backend-api-spec.md](backend-api-spec.md). The build plans are in [plans/](plans/).

## Local setup

You need [uv](https://docs.astral.sh/uv/) and a running PostgreSQL.

```bash
uv sync                                   # creates .venv with Python 3.12 + deps
cp .env.example .env                      # then adjust DATABASE_URL etc.
createdb vibishan && createdb vibishan_test
uv run alembic upgrade head               # create tables
uv run python -m app.seed                 # load demo data (all passwords: password123)
uv run uvicorn app.main:app --reload      # http://localhost:8000/api/v1/health, docs at /docs
```

Seed accounts (username / role): `alice`, `bob` and `carol` are users, `lisa` and `leo` are listeners, and `maya` and `max` are moderators.

## Tests

```bash
uv run pytest                                          # whole suite
uv run pytest tests/test_rooms.py::test_mute_unmute    # one test
```

Tests run against `TEST_DATABASE_URL`, which defaults to `postgresql+psycopg://localhost:5432/vibishan_test`. Migrations are applied automatically, and the database is re-seeded before every test. [tests/test_acceptance.py](tests/test_acceptance.py) runs the spec §11 checklist end to end.

## Testing with Postman

1. Start the server with `uv run uvicorn app.main:app --reload`.
2. In Postman, go to **File → Import** and choose [postman/vibishan.postman_collection.json](postman/vibishan.postman_collection.json). It has 63 requests covering every endpoint, grouped into folders.
3. Run **0. Setup** first. It resets the DB to the seed data and stores a JWT for every seed user in collection variables (`token_alice`, `token_leo`, ...).
4. Run any folder, or the whole collection with the Collection Runner. The "Listen flow" and "Moderate flow" folders chain together: earlier requests save `requestId`, `roomId` and the other ids for later ones. Each request has status assertions.

To use another host, change the `baseUrl` collection variable (default `http://localhost:8000/api/v1`).

To run the collection headlessly, use `npx newman run postman/vibishan.postman_collection.json`.

[postman/curls.sh](postman/curls.sh) has the same flow as plain curl commands. Run it with `bash postman/curls.sh`, or paste any single command into Postman with **Import → Raw text**.

## Environment variables

| Name | Purpose |
|---|---|
| `DATABASE_URL` | Postgres URL (`postgresql+psycopg://...`). In production, use the provider's **pooled** endpoint. |
| `JWT_SECRET` | HS256 signing key. Use a long random string. |
| `JWT_EXPIRES_DAYS` | Token lifetime in days (default 30). |
| `CORS_ORIGINS` | Comma-separated allowed origins, for example `http://localhost:8081`. |
| `ENABLE_DEV_ENDPOINTS` | Set to `true` to expose `POST /api/v1/dev/reset`. |

## Deploying to Vercel

1. Create a Postgres database, such as Neon or Supabase from the Vercel Marketplace, and copy its pooled connection string. Change the scheme to `postgresql+psycopg://`.
2. Set the environment variables above in the Vercel project.
3. Run the migrations from your machine or from CI, never on cold start:
   `DATABASE_URL=<prod url> uv run alembic upgrade head`. Then optionally run `uv run python -m app.seed`.
4. Deploy. Vercel installs `requirements.txt`, and `vercel.json` routes every path to `api/index.py`.

After changing dependencies, regenerate `requirements.txt`:

```bash
uv export --no-dev --no-hashes --no-emit-project -o requirements.txt
```

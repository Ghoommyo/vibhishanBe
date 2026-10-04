# Phase 2: Auth and users (endpoints 1–10)

## Goal
Signup, login and session restore with JWTs, plus profile and settings editing and the provider and user search used by the dashboard.

## Steps
1. Add `app/core/security.py`: argon2 hash and verify, JWT encode (`sub`, `iat`, `exp` from `JWT_EXPIRES_DAYS`) and decode, and a `get_current_user` dependency. A missing, invalid or expired token, or a deleted user, returns 401 `unauthorized` "Please log in again."
2. Add `app/schemas/common.py` (`CamelModel`) and `app/schemas/users.py` (`Profile`, `UserSettings`, `PublicUser`, `RatingSummary`, `ProviderSummary`, `AuthResponse`, and the request bodies).
3. Add `app/services/users.py`:
   - signup: trims input, checks username and email uniqueness case-insensitively, validates username, email and password, and sets defaults
   - login: returns `invalid_credentials` or `wrong_role` with the role label
   - `update_profile`, which also validates email, and `update_settings` (shallow merges)
   - `list_providers(role, q)` (available only, sorted by name) and `search_users(q, exclude=caller)`
   - `rating_summaries(provider_ids)`, a single grouped query
4. Add `app/routers/auth.py` and `app/routers/users.py`. Static paths (`/users/me`, `/users/search`) are declared before `/users/{userId}`.

## Tests
- Signup returns 201 and the response has no password. Duplicate username (in any case) and duplicate email return 409, a bad email returns 422 `invalid_email`, and a short password returns 422.
- Login checks: wrong password returns 401, wrong role returns 403 "This account is registered as a User.", and `/auth/me` works with the token and returns 401 without it.
- Profile and settings updates merge correctly, and changing email to one another user has returns 409.
- `/providers?role=listener` returns Lisa (4.67, 3) and Leo. Unavailable providers are hidden, and `q` filters.
- `/users/search` returns only users and excludes the caller.

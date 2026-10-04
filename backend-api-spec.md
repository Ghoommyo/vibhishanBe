# Vibishan Backend API Specification

Spec for building the Vibishan backend with **Python + FastAPI + PostgreSQL**, deployed on **Vercel (free tier)**.

This document is self-contained: it is the contract the React Native (Expo) app expects. The app currently runs against an in-app mock backend; every endpoint below replaces one mock function, and the behaviour, validation rules, error codes and user-facing messages must match exactly so the app can switch over without UI changes.

---

## 1. Product overview

Vibishan connects people who want to talk with trained helpers.

- **Roles** (fixed at signup):
  - `user` — requests sessions.
  - `listener` — runs 1:1 *listening* sessions.
  - `moderator` — runs *moderated* group sessions between a requester and at least one other user.
- **Lifecycle of a session**
  1. A user sends a **request** (listen → one request per selected listener; moderate → one request with a moderator + participants).
  2. **Approval**: for a moderated session, every participant must accept first; only then is the moderator asked. For a listening session, only the listener has to accept.
  3. A **chatroom** is created together with the request (status `pending`), becomes `active` when the provider accepts, or `rejected` if anyone declines.
  4. Members chat. Messages can be **starred**. A moderator can **mute** members.
  5. Each member submits a **closing note** — called *Conclusion* (members), *Observation* (listener) or *Verdict* (moderator). After submitting, a member can only read.
  6. The room **closes**: immediately when the moderator submits the verdict; for listening rooms, once every member has submitted.
  7. Members (not the provider) **rate** the provider 1–5 stars with optional feedback.
  8. Anyone in the room can view the **summary** (starred messages, conclusions, observation/verdict).
- **Notifications** are generated server-side for request events; the app polls them.
- **Provider analytics**: listeners/moderators see counts, ratings, a weekly chart and feedback.

---

## 2. Tech stack

| Concern | Choice |
|---|---|
| Framework | FastAPI |
| Validation / schemas | Pydantic v2 |
| ORM | SQLAlchemy 2.x (sync is fine; async optional) |
| Migrations | Alembic |
| DB driver | `psycopg[binary]` v3 |
| Auth | JWT (`PyJWT`), HS256 |
| Password hashing | `passlib[argon2]` or `bcrypt` |
| Database | PostgreSQL (Neon or Supabase via the Vercel Marketplace) |
| Hosting | Vercel Python runtime (serverless functions) |

---

## 3. Vercel deployment constraints

These constraints must shape the generated code:

1. **Serverless, stateless.** Each request may hit a fresh instance. No in-memory caches, sessions, background tasks, schedulers or WebSockets. The app already uses **polling** (chat every 2–3 s, notification bell every 3 s), so plain HTTP is enough.
2. **Entry point.** `api/index.py` must expose the FastAPI instance as `app`:
   ```python
   # api/index.py
   from app.main import app  # noqa: F401
   ```
   `vercel.json` rewrites every path to it:
   ```json
   {
     "rewrites": [{ "source": "/(.*)", "destination": "/api/index" }]
   }
   ```
3. **Database connections.** Use the provider's **pooled** connection string (Neon `-pooler` host / Supabase transaction pooler on port 6543). Create the engine with `poolclass=NullPool` (or `pool_size=1, max_overflow=0, pool_pre_ping=True`). Never open connections at import time beyond creating the engine.
4. **Migrations** run from a developer machine or CI (`alembic upgrade head`), never on cold start.
5. **Cold starts.** Keep imports light; no heavy startup work.
6. **Environment variables**

   | Name | Example | Purpose |
   |---|---|---|
   | `DATABASE_URL` | `postgresql+psycopg://user:pass@host/db?sslmode=require` | Pooled Postgres URL |
   | `JWT_SECRET` | long random string | Token signing |
   | `JWT_EXPIRES_DAYS` | `30` | Token lifetime |
   | `CORS_ORIGINS` | `http://localhost:8081,https://your-web-app.vercel.app` | Comma-separated; Expo web dev server is `http://localhost:8081` |
   | `ENABLE_DEV_ENDPOINTS` | `true` / `false` | Enables `POST /dev/reset` |

7. **CORS.** Enable `CORSMiddleware` with `CORS_ORIGINS`, allowing the `Authorization` and `Content-Type` headers. Native iOS/Android clients don't need CORS.

---

## 4. API conventions

### 4.1 Base URL
All endpoints are under **`/api/v1`**, e.g. `POST /api/v1/auth/login`.

### 4.2 JSON shape
- Wire format is **camelCase** (matches the app's TypeScript types). In Pydantic use
  `model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)` and return with `by_alias=True` (FastAPI: `response_model_by_alias=True`, the default).
- **Timestamps are integers: milliseconds since Unix epoch** (`Date.now()` in JS). Store as `timestamptz`, convert at the API edge.
- **IDs are opaque strings.** Store as `text` primary keys. Generate new ids as `<prefix>_<random>` with prefixes `u_`, `req_`, `room_`, `msg_`, `ntf_` (e.g. `room_lx3k9a2b7f`). Seed data uses readable ids such as `u_alice`, `room_seed1`.
- Optional/nullable fields are returned as `null`, never omitted.

### 4.3 Authentication
- `POST /auth/login` and `POST /auth/signup` return `{ "token": "<jwt>", "user": PublicUser }`.
- All other endpoints (except `GET /health`) require `Authorization: Bearer <jwt>`.
- JWT claims: `sub` = user id, `exp`, `iat`.
- Missing/invalid/expired token, or a token whose user no longer exists → `401 unauthorized`, message `"Please log in again."`.
- The client stores the token; logout is client-side (token discarded).

### 4.4 Errors
Every error response has this body:
```json
{ "error": { "code": "forbidden", "message": "Only the moderator can mute." } }
```
`message` is shown to the end user as-is, so use the exact messages listed per endpoint.

| `code` | HTTP status | Meaning |
|---|---|---|
| `unauthorized` | 401 | Not logged in / bad token |
| `invalid_credentials` | 401 | Wrong username or password |
| `wrong_role` | 403 | Logged in with the wrong role tab |
| `forbidden` | 403 | Action not allowed in the current state |
| `not_found` | 404 | Entity missing, or caller has no access to it |
| `closed` | 409 | Request already resolved |
| `username_taken` | 409 | Signup conflict |
| `email_taken` | 409 | Signup/profile conflict |
| `validation` | 422 | Business validation failure |
| `invalid_email` | 422 | Bad email format |

Also map FastAPI's own `RequestValidationError` (malformed body) to `422` with code `validation` and a short readable message, so the envelope is always the same.

Implement as an `ApiError(code, message)` exception with a registered handler that looks up the status from the table above.

---

## 5. Data models

These are the response/request shapes (TypeScript notation, which maps 1:1 to Pydantic models).

### 5.1 Enums
```ts
type Role = 'user' | 'listener' | 'moderator';
type ProviderRole = 'listener' | 'moderator';
type RequestKind = 'listen' | 'moderate';
type ApprovalState = 'pending' | 'accepted' | 'rejected';
type RoomStatus = 'pending' | 'active' | 'closed' | 'rejected';
type RoomRole = 'member' | 'listener' | 'moderator';   // caller's role inside a room
type NotificationKind = 'request_sent' | 'request_received' | 'request_update';
```

### 5.2 Users
```ts
type Profile = {
  name: string;          // display name; defaults to username at signup
  phone: string;         // default ''
  bio: string;           // default ''
  expertise: string[];   // only meaningful for providers; default []
};

type UserSettings = {
  notifyRequests: boolean;       // default true; see notification rule in §7
  showMessagePreviews: boolean;  // default true; client-only preference
  available: boolean;            // default true; providers with false are hidden from GET /providers
};

type PublicUser = {
  id: string;
  username: string;
  email: string;
  role: Role;
  profile: Profile;
  settings: UserSettings;
  createdAt: number;
};  // the password (hash) is NEVER returned

type RatingSummary = { average: number | null; count: number };  // average is null when count = 0

type ProviderSummary = PublicUser & { rating: RatingSummary };

type AuthResponse = { token: string; user: PublicUser };
```

### 5.3 Requests
```ts
type ServiceRequest = {
  id: string;
  kind: RequestKind;
  requesterId: string;
  providerId: string;
  participantIds: string[];                   // [] for listen requests
  approvals: Record<string, ApprovalState>;   // keys = participantIds + providerId (NOT the requester)
  status: ApprovalState;
  roomId: string;
  createdAt: number;
};

type SentRequestsResult = { providerNames: string[]; participantNames: string[] };
```

### 5.4 Rooms and messages
```ts
type Closure = { userId: string; text: string; at: number };
type Rating = { byId: string; stars: number; feedback: string; at: number };

type Room = {
  id: string;
  kind: RequestKind;
  requestId: string;
  requesterId: string;
  providerId: string;
  memberIds: string[];                 // ordered: [requester, ...participants, provider]
  status: RoomStatus;
  mutedIds: string[];
  closures: Record<string, Closure>;   // keyed by userId
  ratings: Rating[];
  createdAt: number;
  closedAt: number | null;
};

type Message = {
  id: string;
  roomId: string;
  senderId: string;
  text: string;
  starredBy: string[];   // user ids who starred it
  createdAt: number;
};

type MessageWithSender = Message & { sender: PublicUser };

type RoomListItem = {
  room: Room;
  provider: PublicUser;
  others: PublicUser[];          // all members except the caller, in memberIds order
  lastMessage: Message | null;
  lastActivity: number;          // max(room.createdAt, lastMessage?.createdAt ?? 0, room.closedAt ?? 0)
};

type RoomDetail = {
  room: Room;
  members: PublicUser[];         // in memberIds order
  myRole: RoomRole;
  canSend: boolean;              // sendBlockedReason === null
  sendBlockedReason: string | null;
  hasSubmitted: boolean;         // caller has a closure
  needsRating: boolean;          // room closed && myRole === 'member' && caller hasn't rated
};

type RoomSummary = {
  room: Room;
  provider: PublicUser;
  starred: MessageWithSender[];                         // messages with ≥1 star, chronological
  comments: { user: PublicUser; text: string; at: number }[];  // non-provider closures, oldest first
  observation: { user: PublicUser; text: string } | null;      // provider closure if kind = listen
  verdict: { user: PublicUser; text: string } | null;          // provider closure if kind = moderate
};
```

### 5.5 Notifications
```ts
type AppNotification = {
  id: string;
  userId: string;          // recipient
  kind: NotificationKind;
  requestId: string;
  text: string;
  read: boolean;
  createdAt: number;
};

type NotificationItem = AppNotification & {
  request: ServiceRequest;
  requester: PublicUser;
  provider: PublicUser;
  participants: PublicUser[];
  actionable: boolean;     // kind === 'request_received' && request.status === 'pending'
                           //   && request.approvals[caller] === 'pending'
};
```

### 5.6 Analytics
```ts
type ProviderStats = {
  listeningDone: number;          // caller's closed rooms with kind = listen
  moderationDone: number;         // caller's closed rooms with kind = moderate
  activeSessions: number;         // caller's rooms with status = active
  averageRating: number | null;
  ratingCount: number;
  ratingDistribution: number[];   // length 5; index 0 = count of 1-star ... index 4 = 5-star
  weekly: { label: string; value: number; start: number; end: number }[];  // 8 buckets, oldest first
  feedback: { by: PublicUser; stars: number; text: string; at: number }[]; // non-empty feedback only, newest first
};
```

---

## 6. Endpoints

`Auth: required` unless stated. "Caller" = the user identified by the token. Throughout, **display name** = `profile.name` if non-empty, else `username`.

### 6.0 Index

| # | Method | Path | Purpose |
|---|---|---|---|
| 1 | POST | `/auth/signup` | Create account and log in |
| 2 | POST | `/auth/login` | Log in |
| 3 | GET | `/auth/me` | Restore session from token |
| 4 | POST | `/auth/logout` | Log out (no-op) |
| 5 | GET | `/users/me` | Own profile + rating |
| 6 | PATCH | `/users/me/profile` | Edit profile/email |
| 7 | PATCH | `/users/me/settings` | Edit settings |
| 8 | GET | `/users/{userId}` | Any user's public profile |
| 9 | GET | `/providers` | List available listeners/moderators |
| 10 | GET | `/users/search` | Find users to add as participants |
| 11 | POST | `/requests/listen` | Send listening request(s) |
| 12 | POST | `/requests/moderate` | Send a moderation request |
| 13 | POST | `/requests/{requestId}/respond` | Accept / reject |
| 14 | GET | `/rooms` | Caller's chatrooms |
| 15 | GET | `/rooms/{roomId}` | Room detail + caller permissions |
| 16 | GET | `/rooms/{roomId}/messages` | Messages |
| 17 | POST | `/rooms/{roomId}/messages` | Send message |
| 18 | POST | `/messages/{messageId}/star` | Toggle star |
| 19 | POST | `/rooms/{roomId}/closure` | Submit closing note |
| 20 | PUT | `/rooms/{roomId}/members/{userId}/mute` | Mute / unmute |
| 21 | POST | `/rooms/{roomId}/ratings` | Rate provider |
| 22 | GET | `/rooms/{roomId}/summary` | Session summary |
| 23 | GET | `/notifications` | Caller's notifications |
| 24 | GET | `/notifications/unread-count` | Badge count |
| 25 | POST | `/notifications/read-all` | Mark all read |
| 26 | GET | `/analytics/provider` | Provider dashboard stats |
| 27 | POST | `/dev/reset` | Reset DB to seed (dev only) |
| 28 | GET | `/health` | Health check |

---

### 6.1 Auth

#### 1. `POST /auth/signup` — Auth: none
Body:
```json
{ "username": "dave", "email": "Dave@Example.com", "password": "secret123", "role": "user" }
```
Rules:
- Trim `username`. Trim + lowercase `email`.
- Username unique **case-insensitively** → else `409 username_taken` "That username is already taken."
- Email unique (lowercased) → else `409 email_taken` "An account with that email already exists."
- Hash the password.
- Defaults: `profile = { name: username, phone: "", bio: "", expertise: [] }`, `settings = { notifyRequests: true, showMessagePreviews: true, available: true }`.
- Recommended extra validation (`422 validation`): username 3–30 chars of letters/digits/`_`/`.`; valid email format (`invalid_email` "Enter a valid email."); password ≥ 8 chars; role ∈ Role.

Response `201`: `AuthResponse`.

#### 2. `POST /auth/login` — Auth: none
Body:
```json
{ "username": "alice", "password": "password123", "role": "user" }
```
Rules:
- Find user by `lower(username) = lower(trim(username))`.
- Not found or bad password → `401 invalid_credentials` "Incorrect username or password."
- `user.role != role` → `403 wrong_role` "This account is registered as a {RoleLabel}." where RoleLabel is `User` / `Listener` / `Moderator`.

Response `200`: `AuthResponse`.

#### 3. `GET /auth/me`
Validates the token (used at app start). Response `200`: `PublicUser`. Token invalid or user deleted → `401 unauthorized`.

#### 4. `POST /auth/logout`
Stateless; returns `204`. (The client drops its token.)

---

### 6.2 Users

#### 5. `GET /users/me`
Response: `ProviderSummary` — caller's `PublicUser` plus `rating` (see rating summary, §7.8). Users with role `user` simply get `{ average: null, count: 0 }`.

#### 6. `PATCH /users/me/profile`
Body (all optional):
```json
{ "name": "Alice S.", "phone": "+91 ...", "bio": "...", "expertise": ["Stress"], "email": "new@x.com" }
```
Rules:
- Only provided fields change (shallow merge into profile).
- If `email` is present: trim + lowercase; must match `^\S+@\S+\.\S+$` else `422 invalid_email` "Enter a valid email."; must not belong to another user else `409 email_taken` "An account with that email already exists."

Response: updated `PublicUser`.

#### 7. `PATCH /users/me/settings`
Body (all optional): `{ "notifyRequests": false, "showMessagePreviews": true, "available": false }`.
Shallow merge. Response: updated `PublicUser`.

#### 8. `GET /users/{userId}`
Response: `PublicUser`. Missing → `404 not_found` "User not found."

#### 9. `GET /providers?role={listener|moderator}&q={text}`
- `role` required (`listener` or `moderator`).
- Returns users with that role **and** `settings.available = true`.
- `q` (optional): case-insensitive substring match on `username` OR `profile.name`; empty/whitespace `q` matches all.
- Response: `ProviderSummary[]` (each with `rating`). Order: by `profile.name` ascending (any stable order is acceptable).

#### 10. `GET /users/search?q={text}`
- Returns users with role `user`, **excluding the caller**, filtered by `q` like above.
- Response: `PublicUser[]`.

---

### 6.3 Requests

Creating any request also creates its room (§7.1).

#### 11. `POST /requests/listen`
Body: `{ "providerIds": ["u_lisa", "u_leo"] }`
Rules:
- Empty list → `422 validation` "Select at least one listener."
- Each id must exist (`404 not_found` "User not found.") and have role `listener`, else `422 validation` "{name} is not a listener."
- Validate all ids **before** creating anything (all-or-nothing).
- For **each** provider: create one `listen` request + room with no participants, then notify:
  - provider: `request_received` — "{requesterName} requested a listening session."
  - caller: `request_sent` — "You sent a listening request to {providerName}."

Response `201`: `SentRequestsResult` = `{ providerNames: [names in input order], participantNames: [] }`.

#### 12. `POST /requests/moderate`
Body: `{ "providerId": "u_maya", "participantIds": ["u_bob", "u_carol"] }`
Rules:
- Deduplicate `participantIds` and remove the caller.
- None left → `422 validation` "Add at least one participant."
- Provider must exist and be role `moderator` → else `422 validation` "{name} is not a moderator."
- Each participant must exist and be role `user` → else `422 validation` "{name} can't be added as a participant."
- Create one `moderate` request + room.
- Notify:
  - each participant: `request_received` — "{requesterName} invited you to a session moderated by {moderatorName}."
  - caller: `request_sent` — "You sent a moderation request to {moderatorName} with {participantList}."
  - The **moderator is not notified yet** (see §7.2).

`participantList` formatting: 1 name → `"Bob"`; 2 → `"Bob and Carol"`; 3+ → `"Bob, Carol and Dan"` (no Oxford comma).

Response `201`: `{ providerNames: [moderatorName], participantNames: [...] }`.

#### 13. `POST /requests/{requestId}/respond`
Body: `{ "accept": true }`
Full state machine in §7.2. Errors, checked in this order:
- Request missing → `404 not_found` "Request not found."
- `request.status != pending` → `409 closed` "This request has already been resolved."
- Caller is not in `approvals` or their approval isn't `pending` → `403 forbidden` "You have already responded."
- Caller is the moderator of a `moderate` request and not all participants have accepted → `403 forbidden` "Waiting for all participants to accept first."

Response: updated `ServiceRequest`.

---

### 6.4 Rooms and chat

**Access rule for every room endpoint:** if the room doesn't exist **or the caller isn't in `memberIds`** → `404 not_found` "Chatroom not found."

#### 14. `GET /rooms`
All rooms where the caller is a member (any status), as `RoomListItem[]`, sorted by `lastActivity` descending.

#### 15. `GET /rooms/{roomId}`
Response: `RoomDetail`. `myRole` and `sendBlockedReason` per §7.3–7.4.

#### 16. `GET /rooms/{roomId}/messages?after={ms}`
- Response: `MessageWithSender[]` in ascending `createdAt` order (tie-break by id).
- `after` (optional): only messages with `createdAt > after`. When omitted, return all. (The current app re-fetches all messages; `after` is for cheaper polling later.)

#### 17. `POST /rooms/{roomId}/messages`
Body: `{ "text": "Hello" }`
- Trim; empty → `422 validation` "Message is empty."
- If `sendBlockedReason(room, caller)` is not null → `403 forbidden` with that reason as the message.
- Response `201`: the created `Message` (`starredBy: []`).

#### 18. `POST /messages/{messageId}/star`
- Message missing → `404 not_found` "Message not found."
- Caller must be a member of the message's room (else `404` "Chatroom not found.").
- Toggles the caller in `starredBy`. Allowed in any room status.
- Response: updated `Message`.

#### 19. `POST /rooms/{roomId}/closure`
Body: `{ "text": "Felt lighter after talking." }` (trimmed; empty text is allowed)
- `room.status != active` → `403 forbidden` "This chat is not open."
- Caller already has a closure → `403 forbidden` "You have already submitted."
- Store closure `{ userId, text, at: now }`, then apply closing rule (§7.5).
- Response: updated `Room`.

#### 20. `PUT /rooms/{roomId}/members/{userId}/mute`
Body: `{ "muted": true }`
- Caller's room role must be `moderator` → else `403 forbidden` "Only the moderator can mute."
- `userId` is the caller or not a room member → `422 validation` "Cannot mute this member."
- Add/remove `userId` in `mutedIds` (idempotent, no duplicates).
- Response: updated `Room`.

#### 21. `POST /rooms/{roomId}/ratings`
Body: `{ "stars": 5, "feedback": "Very helpful." }`
- `stars` not an integer in 1..5 → `422 validation` "Choose between 1 and 5 stars." (checked before loading the room)
- `room.status != closed` → `403 forbidden` "You can rate once the chat is closed."
- Caller's room role isn't `member` → `403 forbidden` "Providers do not rate themselves."
- Caller already rated → `403 forbidden` "You have already rated."
- Append `{ byId, stars, feedback: trim(feedback), at: now }`.
- Response `201`: updated `Room`.

#### 22. `GET /rooms/{roomId}/summary`
Response: `RoomSummary` (§5.4). Available for any room the caller is a member of (the app opens it for closed rooms).

---

### 6.5 Notifications

#### 23. `GET /notifications`
- The caller's notifications, newest first, each expanded to a `NotificationItem` with the related request, requester, provider, participants and `actionable` flag.
- Skip notifications whose request no longer exists.

#### 24. `GET /notifications/unread-count`
Response: `{ "count": 3 }` — caller's notifications with `read = false`. Polled every ~3 s; keep it a single cheap `COUNT(*)` query.

#### 25. `POST /notifications/read-all`
Sets `read = true` for all of the caller's notifications. Response `204`.

---

### 6.6 Analytics

#### 26. `GET /analytics/provider?tzOffset={minutes}`
For the caller as provider (meaningful for listeners/moderators; a plain user just gets zeros).
- `mine` = rooms where `providerId = caller`; `closed` = those with status `closed`.
- `listeningDone`, `moderationDone`, `activeSessions` — see §5.6.
- `averageRating` / `ratingCount` = rating summary (§7.8).
- `ratingDistribution` = counts of 1..5-star ratings across `mine`.
- `weekly`: 8 buckets, oldest first. For `i` in `0..7`, `weeksAgo = 7 - i`, `end = now - weeksAgo * 7d`, `start = end - 7d`; `value` = closed rooms with `start < closedAt <= end`. `label` = `"Now"` for the last bucket, otherwise `"{day}/{month}"` (no zero-padding) of the date `start + 1ms`, rendered in the client's timezone.
- `tzOffset` (optional, default 0) is JavaScript's `new Date().getTimezoneOffset()` (minutes, e.g. `-330` for IST); local time = UTC − tzOffset minutes.
- `feedback` = ratings on `mine` with non-empty feedback, newest first, with `by` = rater's `PublicUser`.

---

### 6.7 Dev / ops

#### 27. `POST /dev/reset`
Only registered when `ENABLE_DEV_ENDPOINTS=true` (otherwise `404`). Truncates all tables and re-inserts the seed (§9). Auth: none (it's dev-only). Response `204`. The app's Settings → "Reset demo data" calls this.

#### 28. `GET /health` — Auth: none
Runs `SELECT 1`. Response `{ "status": "ok" }`, or `503` if the DB is unreachable.

---

## 7. Business rules (authoritative)

Put these in a `services/` layer, not in routers. Every mutating endpoint runs in **one DB transaction**. In `respond`, `submitClosure`, `rate` and `setMuted`, lock the request/room row with `SELECT … FOR UPDATE` to avoid races between members acting at the same time.

### 7.1 Creating a request + room
```
request = {
  kind, requesterId = caller, providerId, participantIds,
  approvals = { each participant: pending, provider: pending },   // requester is NOT in approvals
  status = pending, roomId = new id, createdAt = now
}
room = {
  id = request.roomId, kind, requestId, requesterId, providerId,
  memberIds = [requester, ...participants, provider],
  status = pending, mutedIds = [], closures = {}, ratings = [],
  createdAt = now, closedAt = null
}
```
The room exists from the start so it shows up in the chat list as "pending".

### 7.2 Respond state machine
Let `others = [requester, ...participants]` minus the caller. `myName` = caller's display name.

1. Set `approvals[caller] = accepted | rejected`.
2. **Reject** (anyone): `request.status = rejected`, `room.status = rejected`. Notify every id in `others`: `request_update` — "{myName} declined the request."
3. **Accept by provider**: `request.status = accepted`, `room.status = active`. Notify every id in `others`: `request_update` — "{myName} accepted. The chatroom is now open."
4. **Accept by a participant** (moderate only):
   - Notify the requester: `request_update` — "{myName} accepted your invitation."
   - If now **all** participants have accepted, notify the moderator: `request_received` — "{requesterName} requested a moderated session with {participantList}."
   - Request and room stay `pending` until the moderator responds.

### 7.3 Room role
```
roomRole(room, userId) =
  'member'    if userId != room.providerId
  'listener'  if provider and room.kind == 'listen'
  'moderator' if provider and room.kind == 'moderate'
```
Closing-note labels (UI only): member → Conclusion, listener → Observation, moderator → Verdict.

### 7.4 sendBlockedReason(room, userId)
First matching rule wins:

| Condition | Reason |
|---|---|
| `room.status == pending` | "Waiting for everyone to approve." |
| `room.status == rejected` | "This request was declined." |
| `room.status == closed` | "This chat is closed." |
| user has a closure | "You have submitted and left this chat." |
| user in `mutedIds` | "You have been muted by the moderator." |
| otherwise | `null` (can send) |

### 7.5 Closing rule (after a closure is stored)
The room closes (`status = closed`, `closedAt = now`) if:
- the submitter's room role is `moderator`, **or**
- `room.kind == listen` and **every** id in `memberIds` has a closure.

A moderated room closes **only** via the moderator's verdict, even if all members have submitted.

### 7.6 Ratings
Only `member`s rate, once per room, only when the room is `closed`. `needsRating = room.status == closed && myRole == member && caller has not rated`.

### 7.7 Notifications (`notify` helper)
```
notify(userId, kind, requestId, text):
  insert notification {
    id, userId, kind, requestId, text, createdAt = now,
    read = (kind == 'request_update' and recipient.settings.notifyRequests == false)
  }
```
Users who turned off request updates still see them in the list, just without contributing to the unread badge. `request_sent` and `request_received` are always created unread.

### 7.8 Rating summary
For a provider: all `stars` across ratings on rooms where `providerId = provider`.
`{ average: mean(stars) or null if none, count }`. Return `average` as a float (not rounded).

### 7.9 Summary
- `starred` = room's messages with at least one star, chronological, with `sender`.
- `comments` = closures from anyone other than the provider, oldest first.
- Provider's closure (if any) → `observation` when `kind = listen`, `verdict` when `kind = moderate`; the other is `null`.

---

## 8. PostgreSQL schema

Normalized tables; the API assembles the nested shapes (`approvals`, `memberIds`, `closures`, etc.).

```sql
CREATE TABLE users (
  id            text PRIMARY KEY,
  username      text NOT NULL,
  email         text NOT NULL,
  password_hash text NOT NULL,
  role          text NOT NULL CHECK (role IN ('user','listener','moderator')),
  name          text NOT NULL DEFAULT '',
  phone         text NOT NULL DEFAULT '',
  bio           text NOT NULL DEFAULT '',
  expertise     text[] NOT NULL DEFAULT '{}',
  notify_requests       boolean NOT NULL DEFAULT true,
  show_message_previews boolean NOT NULL DEFAULT true,
  available             boolean NOT NULL DEFAULT true,
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX users_username_lower ON users (lower(username));
CREATE UNIQUE INDEX users_email_lower    ON users (lower(email));
CREATE INDEX users_role ON users (role);

CREATE TABLE service_requests (
  id           text PRIMARY KEY,
  kind         text NOT NULL CHECK (kind IN ('listen','moderate')),
  requester_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  provider_id  text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  status       text NOT NULL CHECK (status IN ('pending','accepted','rejected')),
  room_id      text NOT NULL UNIQUE,
  created_at   timestamptz NOT NULL DEFAULT now()
);

-- participants of a request, ordered (empty for listen requests)
CREATE TABLE request_participants (
  request_id text NOT NULL REFERENCES service_requests(id) ON DELETE CASCADE,
  user_id    text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  position   int  NOT NULL,
  PRIMARY KEY (request_id, user_id)
);

-- one row per approver (participants + provider)
CREATE TABLE request_approvals (
  request_id text NOT NULL REFERENCES service_requests(id) ON DELETE CASCADE,
  user_id    text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  state      text NOT NULL CHECK (state IN ('pending','accepted','rejected')),
  PRIMARY KEY (request_id, user_id)
);

CREATE TABLE rooms (
  id           text PRIMARY KEY,
  kind         text NOT NULL CHECK (kind IN ('listen','moderate')),
  request_id   text NOT NULL UNIQUE REFERENCES service_requests(id) ON DELETE CASCADE,
  requester_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  provider_id  text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  status       text NOT NULL CHECK (status IN ('pending','active','closed','rejected')),
  created_at   timestamptz NOT NULL DEFAULT now(),
  closed_at    timestamptz
);
CREATE INDEX rooms_provider ON rooms (provider_id, status);

-- members in order: requester, participants..., provider
CREATE TABLE room_members (
  room_id  text NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
  user_id  text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  position int  NOT NULL,
  PRIMARY KEY (room_id, user_id)
);
CREATE INDEX room_members_user ON room_members (user_id);

CREATE TABLE room_mutes (
  room_id text NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
  user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  PRIMARY KEY (room_id, user_id)
);

CREATE TABLE room_closures (
  room_id text NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
  user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  text    text NOT NULL,
  at      timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (room_id, user_id)
);

CREATE TABLE room_ratings (
  room_id  text NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
  by_id    text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  stars    int  NOT NULL CHECK (stars BETWEEN 1 AND 5),
  feedback text NOT NULL DEFAULT '',
  at       timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (room_id, by_id)
);

CREATE TABLE messages (
  id         text PRIMARY KEY,
  room_id    text NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
  sender_id  text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  text       text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX messages_room_created ON messages (room_id, created_at);

CREATE TABLE message_stars (
  message_id text NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
  user_id    text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  PRIMARY KEY (message_id, user_id)
);

CREATE TABLE notifications (
  id         text PRIMARY KEY,
  user_id    text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind       text NOT NULL CHECK (kind IN ('request_sent','request_received','request_update')),
  request_id text NOT NULL REFERENCES service_requests(id) ON DELETE CASCADE,
  text       text NOT NULL,
  read       boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX notifications_user_created ON notifications (user_id, created_at DESC);
CREATE INDEX notifications_user_unread  ON notifications (user_id) WHERE NOT read;
```

Mapping notes:
- `users` columns → `PublicUser.profile` (`name, phone, bio, expertise`) and `PublicUser.settings` (`notify_requests → notifyRequests`, ...).
- `ServiceRequest.participantIds` from `request_participants` ordered by `position`; `approvals` from `request_approvals` as a dict.
- `Room.memberIds` from `room_members` ordered by `position`; `mutedIds`, `closures` (dict keyed by user id), `ratings` (ordered by `at`) from their tables.
- `Message.starredBy` from `message_stars`.
- Avoid N+1 queries on list endpoints (`/rooms`, `/notifications`, `/rooms/{id}/messages`): load related rows in bulk (`selectinload` or `WHERE id = ANY(:ids)`) and cache users per request.

---

## 9. Seed data

Seed on `alembic` setup (a `python -m app.seed` command) and on `POST /dev/reset`. Timestamps are relative to the moment of seeding (`now`). `DAY = 24h`.

### 9.1 Users
All passwords: **`password123`** (store hashed). Email: `{username}@vibishan.app`. `createdAt = now - 90 days`. Settings all default (`true`). Phone: `"+91 98765 4321{i}"` where `i` is the 0-based row index.

| i | id | username | role | name | bio | expertise |
|---|---|---|---|---|---|---|
| 0 | `u_alice` | alice | user | Alice Sharma | Product designer who likes long walks. | — |
| 1 | `u_bob` | bob | user | Bob Mehta | Runner, reader, occasional over-thinker. | — |
| 2 | `u_carol` | carol | user | Carol Dsouza | Grad student juggling deadlines. | — |
| 3 | `u_lisa` | lisa | listener | Lisa Kapoor | Patient ear, 5 years of peer support. | Stress, Career, Relationships |
| 4 | `u_leo` | leo | listener | Leo Fernandes | Here to listen without judgement. | Loneliness, Studies |
| 5 | `u_maya` | maya | moderator | Maya Iyer | Certified mediator for group conversations. | Conflict resolution, Family |
| 6 | `u_max` | max | moderator | Max Rao | Keeps discussions fair and on track. | Roommates, Workplace |

### 9.2 Sessions
For session number `n` (1-based, in the order below):
- `requestId = req_seed{n}`, `roomId = room_seed{n}`, `createdAt = now - daysAgo * DAY`.
- Request: `status = pending` if the room is pending, otherwise `accepted`; every approval (participants + provider) has that same state.
- Room: members `[requester, ...participants, provider]`, `mutedIds = []`, `closedAt = createdAt + DAY/2` if closed else `null`.
- Closures and ratings: `at = createdAt + DAY/2`.
- Messages: line `i` (0-based) → `id = msg_seed{n}_{i}`, `createdAt = createdAt + (i+1) * 60s`. A starred line is starred by the **requester**.

Lines marked ★ are starred.

**Session 1** — listen, requester alice, provider lisa, 50 days ago, **closed**
- alice: Work has been overwhelming lately.
- lisa: That sounds exhausting. What feels heaviest right now?
- alice: Mostly the feeling that I can never catch up. ★
- lisa: Would it help to list what is actually due this week?
- alice: Yes, writing it down makes it smaller. ★
- Closures: alice "Felt lighter after talking it through." · lisa "Alice benefits from breaking work into weekly lists."
- Ratings: alice 5 "Lisa was calm and really listened."

**Session 2** — listen, bob → lisa, 36 days ago, **closed**
- bob: Thinking about switching careers.
- lisa: What is drawing you to the change?
- bob: I want work that feels meaningful. ★
- Closures: bob "Good space to think out loud." · lisa "Bob is clear on values, unsure on timing."
- Ratings: bob 4 "Helpful questions, felt heard."

**Session 3** — listen, carol → leo, 22 days ago, **closed**
- carol: Thesis deadline is next month and I feel stuck. ★
- leo: Stuck on writing, or on the research itself?
- carol: Writing. I keep rewriting the intro. ★
- Closures: carol "Will draft the rest before polishing the intro." · leo "Perfectionism on the intro is the blocker."
- Ratings: carol 4 "Leo gave me a practical next step."

**Session 4** — listen, alice → lisa, 9 days ago, **closed**
- alice: Checking in, the weekly list is working! ★
- lisa: That is great to hear. Anything new on your mind?
- Closures: alice "Progress feels real." · lisa "Habits are sticking."
- Ratings: alice 5 "Always a good conversation."

**Session 5** — moderate, alice → maya, participants [bob], 29 days ago, **closed**
- maya: Welcome both. Alice, would you like to start?
- alice: We disagreed about splitting the project credit. ★
- bob: I felt my part was overlooked in the review. ★
- maya: Can you each name one thing the other did well?
- alice: Bob handled all the testing, honestly. ★
- Closures: alice "I will credit Bob explicitly next time." · bob "Glad we talked, feels fair now." · maya "Both agree to list contributions in shared reviews going forward."
- Ratings: alice 5 "Maya kept it fair." · bob 4 "Good structure."

**Session 6** — moderate, carol → max, participants [bob], 15 days ago, **closed**
- max: Let us keep this about the shared flat chores.
- carol: Dishes pile up for days. ★
- bob: I can take dishes if you take bins. ★
- Closures: carol "Rota agreed." · max "Weekly rota: Bob dishes, Carol bins, review in a month."
- Ratings: carol 4 "Quick and practical." · bob 3 "A bit rushed."

**Session 7** — moderate, bob → maya, participants [carol], 4 days ago, **closed**
- maya: Following up on the flat rota.
- bob: Mostly working, bins got missed twice. ★
- carol: Fair, I will set a reminder. ★
- Closures: bob "Good follow up." · maya "Rota stays, Carol adds reminders."
- Ratings: bob 5 "Maya follows up properly."

**Session 8** — listen, carol → lisa, 1 day ago, **active** (live chat to try immediately)
- carol: Hi Lisa, is now a good time?
- lisa: Of course, I am here. What is on your mind?
- No closures, no ratings.

**Session 9** — listen, bob → leo, 0.1 days ago, **pending** (no messages)

### 9.3 Notifications
Both point at `req_seed9`, `createdAt` = session 9's `createdAt`:

| id | userId | kind | text | read |
|---|---|---|---|---|
| `ntf_seed1` | `u_leo` | request_received | Bob Mehta requested a listening session. | false |
| `ntf_seed2` | `u_bob` | request_sent | You sent a listening request to Leo Fernandes. | true |

---

## 10. Suggested project layout

```
vibishan-api/
├── api/
│   └── index.py              # Vercel entry: from app.main import app
├── app/
│   ├── main.py               # FastAPI(), CORS, error handlers, include routers under /api/v1
│   ├── core/
│   │   ├── config.py         # pydantic-settings: env vars
│   │   ├── security.py       # hash/verify password, create/decode JWT, get_current_user dependency
│   │   └── errors.py         # ApiError + handlers + code→status map
│   ├── db/
│   │   ├── session.py        # engine (NullPool), SessionLocal, get_db dependency
│   │   └── models.py         # SQLAlchemy models for §8
│   ├── schemas/              # Pydantic camelCase models for §5
│   ├── services/             # business rules §7 (auth, users, requests, rooms, notifications, analytics)
│   ├── routers/              # thin HTTP layer: auth, users, requests, rooms, notifications, analytics, dev, health
│   └── seed.py               # §9; runnable as `python -m app.seed`
├── alembic/                  # migrations
├── alembic.ini
├── tests/                    # pytest + httpx TestClient against a test Postgres
├── requirements.txt
├── vercel.json
└── .env.example
```

`requirements.txt` (pin versions when generating):
```
fastapi
pydantic
pydantic-settings
sqlalchemy
psycopg[binary]
alembic
pyjwt
passlib[argon2]
```

---

## 11. Acceptance checklist

Run against a freshly seeded DB. Every step should behave exactly as described.

1. `POST /auth/login` alice/password123/user → token. Same with role `listener` → `403 wrong_role` "This account is registered as a User."
2. `GET /providers?role=listener` → lisa and leo with ratings (lisa: average 4.67, count 3).
3. As alice: `POST /requests/listen {providerIds:[u_leo]}` → leo gets an unread `request_received`; alice gets a `request_sent`; `GET /rooms` shows a pending room.
4. As alice: `POST /rooms/{that room}/messages` → `403` "Waiting for everyone to approve."
5. As leo: `POST /requests/{id}/respond {accept:true}` → room `active`; alice gets "Leo Fernandes accepted. The chatroom is now open."
6. Alice and leo exchange messages; alice stars one.
7. Alice submits closure → room still active, alice can't send ("You have submitted and left this chat."). Leo submits → room `closed`.
8. Alice rates 5 stars → leo's `/analytics/provider` shows the new rating and closed session; leo rating → `403` "Providers do not rate themselves."
9. Moderation: alice → maya with [bob]. Maya tries to respond → `403` "Waiting for all participants to accept first." Bob accepts → maya gets `request_received` "Alice Sharma requested a moderated session with Bob Mehta." Maya accepts → room active.
10. Maya mutes bob → bob's send gets "You have been muted by the moderator." Maya submits verdict → room closes for everyone even though alice and bob didn't submit.
11. Rejection: any approver declines → request & room `rejected`, others notified "{name} declined the request."
12. `notifyRequests=false` for a user → their new `request_update` notifications arrive with `read: true`.
13. `POST /dev/reset` restores the seed.

---

## 12. Notes for wiring the app (client side, later)

- Keep each existing function signature in the app's `src/api/*.ts`; replace the body with a `fetch` to the matching endpoint.
- Store the JWT with `expo-secure-store` on native and `localStorage` on web; send it as `Authorization: Bearer`.
- Convert `{ error: { code, message } }` responses into the app's existing `ApiError(code, message)`.
- `restoreSession` → `GET /auth/me`; `resetDb` → `POST /dev/reset`; `analyticsApi.getProviderStats` passes `tzOffset = new Date().getTimezoneOffset()`.
- Polling via `useApi` needs no change.

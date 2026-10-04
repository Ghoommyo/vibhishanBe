# Phase 3: Requests and notifications (endpoints 11–13, 23–25)

## Goal
Users can send listen and moderate requests, approvers can accept or reject them following the §7.2 state machine, and notifications are created and served.

## Steps
1. Add `app/schemas/requests.py` (`ServiceRequest`, `SentRequestsResult`, bodies) and `app/schemas/notifications.py` (`NotificationItem`, `UnreadCount`).
2. Add `app/services/notifications.py`: `notify()` creates `request_update` notifications pre-read when the recipient has `notifyRequests = false`. It also covers the list (newest first, related rows bulk-loaded, `actionable` flag), the unread count (`COUNT(*)`) and read-all.
3. Add `app/services/requests.py`:
   - `create_request_with_room()` follows §7.1.
   - `send_listen()` validates every id before creating anything, then creates one request and room per provider and sends the notifications.
   - `send_moderate()` dedupes participants, removes the caller, validates, and creates the request. It notifies participants and the caller but not the moderator yet.
   - `respond()` locks the request and room `FOR UPDATE` and checks errors in the order the spec lists them. Reject sets both to rejected and notifies everyone else. A provider accept sets them to accepted and active. A participant accept notifies the requester, and once every participant has accepted, it notifies the moderator.
   - `serialize_requests()` assembles `participantIds` and `approvals` in bulk.
4. Add `app/routers/requests.py` and `app/routers/notifications.py`.

## Tests
- Listen: an empty list returns 422, a non-listener returns 422 "{name} is not a listener.", and nothing is created when validation fails. Multiple providers create multiple rooms, and the notification texts match the spec.
- Moderate: participant checks, the participant-list formatting, and the moderator not being notified initially.
- Respond: a missing request returns 404, a resolved one returns 409, a repeat response returns 403, and an early moderator response returns 403 "Waiting for all participants to accept first." Also covers the reject path and the notifications after full acceptance.
- `notifyRequests=false` means new `request_update` notifications arrive already read. Unread count and read-all work.

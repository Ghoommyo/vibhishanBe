# Phase 4: Rooms and chat (endpoints 14–22)

## Goal
The chatroom list, room detail with the caller's permissions, messaging with stars, closing notes, moderator mute, ratings and the session summary.

## Steps
1. Add `app/schemas/rooms.py`: `Room`, `Closure`, `Rating`, `Message`, `MessageWithSender`, `RoomListItem`, `RoomDetail`, `RoomSummary`, and the bodies.
2. Add `app/services/rooms.py`:
   - `load_room_for_member(room_id, caller, lock=False)` returns 404 "Chatroom not found." when the room is missing or the caller isn't a member.
   - `build_rooms(rooms)` assembles members ordered by position, mutes, closures and ratings in bulk.
   - `room_role()` follows §7.3 and `send_blocked_reason()` follows §7.4.
   - `list_rooms()` adds the last message per room and `lastActivity` and sorts by it descending. `room_detail()` returns `RoomDetail`.
   - `list_messages(after)` sorts by createdAt then id and includes `sender`. `send_message()` covers the empty-text check and the blocked reason.
   - `toggle_star()` returns "Message not found." when the message is missing, and the room-membership 404 otherwise.
   - `submit_closure()` (with the room locked) applies the closing rule from §7.5.
   - `set_muted()` (with the room locked) is for moderators only and rejects self and non-members.
   - `rate()` checks stars before loading the room, then requires the room to be closed and the caller to be a member who hasn't rated yet.
   - `summary()` follows §7.9.
3. Add `app/routers/rooms.py`, which also hosts `/messages/{id}/star`.

## Tests
- Room list order and pending status. A non-member gets 404.
- Every `sendBlockedReason` branch, and an empty message returns 422.
- Star toggles on and off.
- A listen room closes only after every member submits, a moderator verdict closes it immediately, and submitting twice returns 403.
- Mute and unmute, along with the moderator-only and self-mute errors.
- Rating validation order and every rating error.
- Summary contents for seed sessions 1 and 5.

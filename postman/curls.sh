#!/usr/bin/env bash
# Every Vibishan endpoint as a plain curl command.
#
#   bash postman/curls.sh            # runs everything top to bottom against a running server
#
# Any single command can also be pasted into Postman via Import -> Raw text
# (replace $BASE / $TOKEN_* / $ROOM_ID ... with real values first).
set -euo pipefail

BASE="${BASE:-http://localhost:8000/api/v1}"
JSON="Content-Type: application/json"

json_get() { python3 -c "import sys, json; d = json.load(sys.stdin); print(eval('d' + sys.argv[1]))" "$1"; }
show() { echo; echo "### $*"; }

# ---------------------------------------------------------------- 0. Setup
show "Health"
curl -s "$BASE/health"

show "Dev reset (restore seed data; needs ENABLE_DEV_ENDPOINTS=true)"
curl -s -o /dev/null -w "%{http_code}\n" -X POST "$BASE/dev/reset"

login() {  # login <username> <role>  -> prints the JWT
  curl -s -X POST "$BASE/auth/login" -H "$JSON" \
    -d "{\"username\": \"$1\", \"password\": \"password123\", \"role\": \"$2\"}" | json_get "['token']"
}
TOKEN_ALICE=$(login alice user)
TOKEN_BOB=$(login bob user)
TOKEN_CAROL=$(login carol user)
TOKEN_LISA=$(login lisa listener)
TOKEN_LEO=$(login leo listener)
TOKEN_MAYA=$(login maya moderator)
AUTH_ALICE="Authorization: Bearer $TOKEN_ALICE"
AUTH_BOB="Authorization: Bearer $TOKEN_BOB"
AUTH_CAROL="Authorization: Bearer $TOKEN_CAROL"
AUTH_LISA="Authorization: Bearer $TOKEN_LISA"
AUTH_LEO="Authorization: Bearer $TOKEN_LEO"
AUTH_MAYA="Authorization: Bearer $TOKEN_MAYA"
echo "Logged in all seed users."

# ---------------------------------------------------------------- 1. Auth
show "Signup"
NEW_USER="dave_$(date +%s)"
SIGNUP=$(curl -s -X POST "$BASE/auth/signup" -H "$JSON" \
  -d "{\"username\": \"$NEW_USER\", \"email\": \"$NEW_USER@example.com\", \"password\": \"secret123\", \"role\": \"user\"}")
echo "$SIGNUP"
AUTH_NEW="Authorization: Bearer $(echo "$SIGNUP" | json_get "['token']")"

show "Login - wrong role (403)"
curl -s -X POST "$BASE/auth/login" -H "$JSON" \
  -d '{"username": "alice", "password": "password123", "role": "listener"}'

show "Me"
curl -s "$BASE/auth/me" -H "$AUTH_NEW"

show "Logout"
curl -s -o /dev/null -w "%{http_code}\n" -X POST "$BASE/auth/logout" -H "$AUTH_NEW"

# ---------------------------------------------------------------- 2. Users
show "My profile + rating (lisa)"
curl -s "$BASE/users/me" -H "$AUTH_LISA"

show "Update profile"
curl -s -X PATCH "$BASE/users/me/profile" -H "$AUTH_ALICE" -H "$JSON" \
  -d '{"bio": "Product designer who likes long walks.", "phone": "+91 98765 43210"}'

show "Update settings"
curl -s -X PATCH "$BASE/users/me/settings" -H "$AUTH_ALICE" -H "$JSON" \
  -d '{"notifyRequests": true, "showMessagePreviews": true}'

show "Get user by id"
curl -s "$BASE/users/u_bob" -H "$AUTH_ALICE"

show "List listeners"
curl -s "$BASE/providers?role=listener" -H "$AUTH_ALICE"

show "List moderators (q filter)"
curl -s "$BASE/providers?role=moderator&q=maya" -H "$AUTH_ALICE"

show "Search users"
curl -s "$BASE/users/search?q=bo" -H "$AUTH_ALICE"

# ---------------------------------------------------------------- 3. Listen flow
show "Send listen request (alice -> leo)"
curl -s -X POST "$BASE/requests/listen" -H "$AUTH_ALICE" -H "$JSON" -d '{"providerIds": ["u_leo"]}'

LEO_NOTE=$(curl -s "$BASE/notifications" -H "$AUTH_LEO")
REQUEST_ID=$(echo "$LEO_NOTE" | json_get "[0]['requestId']")
ROOM_ID=$(echo "$LEO_NOTE" | json_get "[0]['request']['roomId']")
echo "REQUEST_ID=$REQUEST_ID ROOM_ID=$ROOM_ID"

show "Send before approval (403)"
curl -s -X POST "$BASE/rooms/$ROOM_ID/messages" -H "$AUTH_ALICE" -H "$JSON" -d '{"text": "Hello?"}'

show "Leo accepts"
curl -s -X POST "$BASE/requests/$REQUEST_ID/respond" -H "$AUTH_LEO" -H "$JSON" -d '{"accept": true}'

show "Alice sends a message"
MSG=$(curl -s -X POST "$BASE/rooms/$ROOM_ID/messages" -H "$AUTH_ALICE" -H "$JSON" \
  -d '{"text": "Hi Leo, work has been a lot lately."}')
echo "$MSG"
MESSAGE_ID=$(echo "$MSG" | json_get "['id']")

show "Leo replies"
curl -s -X POST "$BASE/rooms/$ROOM_ID/messages" -H "$AUTH_LEO" -H "$JSON" \
  -d '{"text": "I am here. What feels heaviest right now?"}'

show "Star a message"
curl -s -X POST "$BASE/messages/$MESSAGE_ID/star" -H "$AUTH_ALICE"

show "Room detail"
curl -s "$BASE/rooms/$ROOM_ID" -H "$AUTH_ALICE"

show "List messages"
curl -s "$BASE/rooms/$ROOM_ID/messages" -H "$AUTH_ALICE"

show "Alice submits conclusion"
curl -s -X POST "$BASE/rooms/$ROOM_ID/closure" -H "$AUTH_ALICE" -H "$JSON" -d '{"text": "Felt lighter after talking."}'

show "Leo submits observation (closes room)"
curl -s -X POST "$BASE/rooms/$ROOM_ID/closure" -H "$AUTH_LEO" -H "$JSON" -d '{"text": "Alice needs smaller weekly goals."}'

show "Alice rates leo"
curl -s -X POST "$BASE/rooms/$ROOM_ID/ratings" -H "$AUTH_ALICE" -H "$JSON" -d '{"stars": 5, "feedback": "Very helpful."}'

show "Session summary"
curl -s "$BASE/rooms/$ROOM_ID/summary" -H "$AUTH_ALICE"

# ---------------------------------------------------------------- 4. Moderate flow
show "Send moderate request (alice -> maya with bob)"
curl -s -X POST "$BASE/requests/moderate" -H "$AUTH_ALICE" -H "$JSON" \
  -d '{"providerId": "u_maya", "participantIds": ["u_bob"]}'

BOB_NOTE=$(curl -s "$BASE/notifications" -H "$AUTH_BOB")
MOD_REQUEST_ID=$(echo "$BOB_NOTE" | json_get "[0]['requestId']")
MOD_ROOM_ID=$(echo "$BOB_NOTE" | json_get "[0]['request']['roomId']")
echo "MOD_REQUEST_ID=$MOD_REQUEST_ID MOD_ROOM_ID=$MOD_ROOM_ID"

show "Maya accepts too early (403)"
curl -s -X POST "$BASE/requests/$MOD_REQUEST_ID/respond" -H "$AUTH_MAYA" -H "$JSON" -d '{"accept": true}'

show "Bob accepts"
curl -s -X POST "$BASE/requests/$MOD_REQUEST_ID/respond" -H "$AUTH_BOB" -H "$JSON" -d '{"accept": true}'

show "Maya accepts"
curl -s -X POST "$BASE/requests/$MOD_REQUEST_ID/respond" -H "$AUTH_MAYA" -H "$JSON" -d '{"accept": true}'

show "Maya mutes bob"
curl -s -X PUT "$BASE/rooms/$MOD_ROOM_ID/members/u_bob/mute" -H "$AUTH_MAYA" -H "$JSON" -d '{"muted": true}'

show "Muted bob sends (403)"
curl -s -X POST "$BASE/rooms/$MOD_ROOM_ID/messages" -H "$AUTH_BOB" -H "$JSON" -d '{"text": "Can I speak?"}'

show "Maya unmutes bob"
curl -s -X PUT "$BASE/rooms/$MOD_ROOM_ID/members/u_bob/mute" -H "$AUTH_MAYA" -H "$JSON" -d '{"muted": false}'

show "Maya submits verdict (closes room)"
curl -s -X POST "$BASE/rooms/$MOD_ROOM_ID/closure" -H "$AUTH_MAYA" -H "$JSON" -d '{"text": "Both agree to list contributions."}'

show "Bob rates maya"
curl -s -X POST "$BASE/rooms/$MOD_ROOM_ID/ratings" -H "$AUTH_BOB" -H "$JSON" -d '{"stars": 4, "feedback": "Fair and calm."}'

# ---------------------------------------------------------------- 5. Rooms (seed data)
show "My chatrooms (carol)"
curl -s "$BASE/rooms" -H "$AUTH_CAROL"

show "Messages after timestamp"
curl -s "$BASE/rooms/room_seed8/messages?after=0" -H "$AUTH_CAROL"

show "Summary of a closed seed room"
curl -s "$BASE/rooms/room_seed1/summary" -H "$AUTH_ALICE"

# ---------------------------------------------------------------- 6. Notifications
show "List notifications"
curl -s "$BASE/notifications" -H "$AUTH_ALICE"

show "Unread count"
curl -s "$BASE/notifications/unread-count" -H "$AUTH_ALICE"

show "Mark all read"
curl -s -o /dev/null -w "%{http_code}\n" -X POST "$BASE/notifications/read-all" -H "$AUTH_ALICE"

# ---------------------------------------------------------------- 7. Analytics
show "Provider stats (lisa, IST)"
curl -s "$BASE/analytics/provider?tzOffset=-330" -H "$AUTH_LISA"

echo
echo "Done."

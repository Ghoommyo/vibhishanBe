"""Spec §11 acceptance checklist, run end to end against a freshly seeded DB."""

API = "/api/v1"


def test_acceptance_checklist(client, auth):
    def get(path, who, **params):
        return client.get(f"{API}{path}", headers=auth(who), params=params)

    def post(path, who, body=None):
        return client.post(f"{API}{path}", headers=auth(who), json=body)

    def notes(who):
        return get("/notifications", who).json()

    # 1. Login, and wrong role tab.
    r = client.post(f"{API}/auth/login", json={"username": "alice", "password": "password123", "role": "user"})
    assert r.status_code == 200 and r.json()["token"]
    r = client.post(f"{API}/auth/login", json={"username": "alice", "password": "password123", "role": "listener"})
    assert r.status_code == 403
    assert r.json()["error"] == {"code": "wrong_role", "message": "This account is registered as a User."}

    # 2. Listener list with ratings.
    providers = {p["id"]: p for p in get("/providers", "alice", role="listener").json()}
    assert set(providers) == {"u_lisa", "u_leo"}
    assert round(providers["u_lisa"]["rating"]["average"], 2) == 4.67
    assert providers["u_lisa"]["rating"]["count"] == 3

    # 3. Listening request to leo.
    assert post("/requests/listen", "alice", {"providerIds": ["u_leo"]}).status_code == 201
    leo_note = notes("leo")[0]
    assert leo_note["kind"] == "request_received" and not leo_note["read"]
    assert notes("alice")[0]["kind"] == "request_sent"
    req_id, room_id = leo_note["requestId"], leo_note["request"]["roomId"]
    pending = next(i for i in get("/rooms", "alice").json() if i["room"]["id"] == room_id)
    assert pending["room"]["status"] == "pending"

    # 4. Cannot chat before approval.
    r = post(f"/rooms/{room_id}/messages", "alice", {"text": "Hello?"})
    assert r.status_code == 403 and r.json()["error"]["message"] == "Waiting for everyone to approve."

    # 5. Leo accepts.
    assert post(f"/requests/{req_id}/respond", "leo", {"accept": True}).json()["status"] == "accepted"
    assert get(f"/rooms/{room_id}", "alice").json()["room"]["status"] == "active"
    assert notes("alice")[0]["text"] == "Leo Fernandes accepted. The chatroom is now open."

    # 6. Chat and star.
    m1 = post(f"/rooms/{room_id}/messages", "alice", {"text": "Hi Leo"}).json()
    post(f"/rooms/{room_id}/messages", "leo", {"text": "Hi Alice, I'm listening."})
    assert post(f"/messages/{m1['id']}/star", "alice").json()["starredBy"] == ["u_alice"]

    # 7. Closures.
    assert post(f"/rooms/{room_id}/closure", "alice", {"text": "Thanks"}).json()["status"] == "active"
    r = post(f"/rooms/{room_id}/messages", "alice", {"text": "one more"})
    assert r.json()["error"]["message"] == "You have submitted and left this chat."
    assert post(f"/rooms/{room_id}/closure", "leo", {"text": "Obs"}).json()["status"] == "closed"

    # 8. Rating, analytics, provider can't rate.
    before = get("/analytics/provider", "leo").json()
    assert post(f"/rooms/{room_id}/ratings", "alice", {"stars": 5, "feedback": "Great"}).status_code == 201
    after = get("/analytics/provider", "leo").json()
    assert after["ratingCount"] == before["ratingCount"] + 1
    assert after["listeningDone"] == 2
    assert after["feedback"][0]["text"] == "Great"
    r = post(f"/rooms/{room_id}/ratings", "leo", {"stars": 5})
    assert r.status_code == 403 and r.json()["error"]["message"] == "Providers do not rate themselves."

    # 9. Moderation approval order.
    post("/requests/moderate", "alice", {"providerId": "u_maya", "participantIds": ["u_bob"]})
    mod_req = notes("bob")[0]["request"]
    r = post(f"/requests/{mod_req['id']}/respond", "maya", {"accept": True})
    assert r.status_code == 403 and r.json()["error"]["message"] == "Waiting for all participants to accept first."
    post(f"/requests/{mod_req['id']}/respond", "bob", {"accept": True})
    maya_note = notes("maya")[0]
    assert maya_note["kind"] == "request_received"
    assert maya_note["text"] == "Alice Sharma requested a moderated session with Bob Mehta."
    post(f"/requests/{mod_req['id']}/respond", "maya", {"accept": True})
    mod_room = mod_req["roomId"]
    assert get(f"/rooms/{mod_room}", "alice").json()["room"]["status"] == "active"

    # 10. Mute and verdict.
    client.put(f"{API}/rooms/{mod_room}/members/u_bob/mute", headers=auth("maya"), json={"muted": True})
    r = post(f"/rooms/{mod_room}/messages", "bob", {"text": "hey"})
    assert r.json()["error"]["message"] == "You have been muted by the moderator."
    assert post(f"/rooms/{mod_room}/closure", "maya", {"text": "Verdict"}).json()["status"] == "closed"

    # 11. Rejection.
    post("/requests/listen", "carol", {"providerIds": ["u_lisa"]})
    rej_req = notes("lisa")[0]["request"]
    assert post(f"/requests/{rej_req['id']}/respond", "lisa", {"accept": False}).json()["status"] == "rejected"
    assert get(f"/rooms/{rej_req['roomId']}", "carol").json()["room"]["status"] == "rejected"
    assert notes("carol")[0]["text"] == "Lisa Kapoor declined the request."

    # 12. notifyRequests=false -> request updates arrive read.
    client.patch(f"{API}/users/me/settings", headers=auth("carol"), json={"notifyRequests": False})
    post("/requests/listen", "carol", {"providerIds": ["u_leo"]})
    new_req = notes("leo")[0]["request"]
    post(f"/requests/{new_req['id']}/respond", "leo", {"accept": True})
    update = notes("carol")[0]
    assert update["kind"] == "request_update" and update["read"] is True

    # 13. Dev reset restores the seed.
    assert client.post(f"{API}/dev/reset").status_code == 204
    assert {i["room"]["id"] for i in get("/rooms", "carol").json()} == {
        "room_seed3", "room_seed6", "room_seed7", "room_seed8"}
    assert len(notes("leo")) == 1

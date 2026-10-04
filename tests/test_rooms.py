API = "/api/v1"


def err(r):
    return r.json()["error"]


def detail(client, h, room):
    return client.get(f"{API}/rooms/{room}", headers=h).json()


def send(client, h, room, text="hi"):
    return client.post(f"{API}/rooms/{room}/messages", headers=h, json={"text": text})


def close(client, h, room, text="done"):
    return client.post(f"{API}/rooms/{room}/closure", headers=h, json={"text": text})


def start_moderated(client, auth):
    """alice -> maya with [bob], fully accepted; returns the active room id."""
    client.post(f"{API}/requests/moderate", headers=auth("alice"),
                json={"providerId": "u_maya", "participantIds": ["u_bob"]})
    req = client.get(f"{API}/notifications", headers=auth("bob")).json()[0]["request"]
    client.post(f"{API}/requests/{req['id']}/respond", headers=auth("bob"), json={"accept": True})
    client.post(f"{API}/requests/{req['id']}/respond", headers=auth("maya"), json={"accept": True})
    return req["roomId"]


# ---------- list / detail ----------

def test_room_list_sorted_by_activity(client, auth):
    items = client.get(f"{API}/rooms", headers=auth("bob")).json()
    ids = [i["room"]["id"] for i in items]
    assert ids[0] == "room_seed9"  # pending, newest
    assert set(ids) == {"room_seed2", "room_seed5", "room_seed6", "room_seed7", "room_seed9"}
    acts = [i["lastActivity"] for i in items]
    assert acts == sorted(acts, reverse=True)
    seed9 = items[0]
    assert seed9["room"]["status"] == "pending" and seed9["lastMessage"] is None
    assert [o["id"] for o in seed9["others"]] == ["u_leo"]
    seed5 = next(i for i in items if i["room"]["id"] == "room_seed5")
    assert seed5["room"]["memberIds"] == ["u_alice", "u_bob", "u_maya"]
    assert seed5["lastMessage"]["id"] == "msg_seed5_4"
    assert seed5["lastActivity"] == seed5["room"]["closedAt"]
    assert set(seed5["room"]["closures"]) == {"u_alice", "u_bob", "u_maya"}


def test_room_access_is_404_for_non_members(client, auth):
    for path in ("rooms/room_seed1", "rooms/room_seed1/messages", "rooms/room_nope",
                 "rooms/room_seed1/summary"):
        r = client.get(f"{API}/{path}", headers=auth("bob"))
        assert r.status_code == 404 and err(r) == {"code": "not_found", "message": "Chatroom not found."}


def test_room_detail_permissions(client, auth):
    d = detail(client, auth("carol"), "room_seed8")
    assert d["myRole"] == "member" and d["canSend"] and d["sendBlockedReason"] is None
    assert detail(client, auth("lisa"), "room_seed8")["myRole"] == "listener"
    d = detail(client, auth("bob"), "room_seed9")
    assert d["sendBlockedReason"] == "Waiting for everyone to approve." and not d["canSend"]
    d = detail(client, auth("alice"), "room_seed1")
    assert d["sendBlockedReason"] == "This chat is closed."
    assert d["hasSubmitted"] and not d["needsRating"]
    assert [m["id"] for m in d["members"]] == ["u_alice", "u_lisa"]
    assert detail(client, auth("maya"), "room_seed5")["myRole"] == "moderator"


# ---------- messages ----------

def test_messages_send_and_after(client, auth):
    h = auth("carol")
    msgs = client.get(f"{API}/rooms/room_seed8/messages", headers=h).json()
    assert [m["id"] for m in msgs] == ["msg_seed8_0", "msg_seed8_1"]
    assert msgs[0]["sender"]["id"] == "u_carol"
    r = send(client, h, "room_seed8", "  Thanks  ")
    assert r.status_code == 201
    created = r.json()
    assert created["text"] == "Thanks" and created["starredBy"] == []
    newer = client.get(f"{API}/rooms/room_seed8/messages",
                       params={"after": msgs[-1]["createdAt"]}, headers=h).json()
    assert [m["id"] for m in newer] == [created["id"]]
    none = client.get(f"{API}/rooms/room_seed8/messages",
                      params={"after": created["createdAt"]}, headers=h).json()
    assert none == []


def test_send_blocked(client, auth):
    r = send(client, auth("carol"), "room_seed8", "   ")
    assert r.status_code == 422 and err(r)["message"] == "Message is empty."
    r = send(client, auth("bob"), "room_seed9")
    assert r.status_code == 403 and err(r) == {"code": "forbidden", "message": "Waiting for everyone to approve."}
    assert err(send(client, auth("alice"), "room_seed1"))["message"] == "This chat is closed."
    client.post(f"{API}/requests/req_seed9/respond", headers=auth("leo"), json={"accept": False})
    assert err(send(client, auth("bob"), "room_seed9"))["message"] == "This request was declined."


def test_star_toggle(client, auth):
    h = auth("carol")
    r = client.post(f"{API}/messages/msg_seed8_1/star", headers=h)
    assert r.status_code == 200 and r.json()["starredBy"] == ["u_carol"]
    r = client.post(f"{API}/messages/msg_seed8_1/star", headers=h)
    assert r.json()["starredBy"] == []
    r = client.post(f"{API}/messages/msg_seed1_0/star", headers=h)
    assert r.status_code == 404 and err(r)["message"] == "Chatroom not found."
    r = client.post(f"{API}/messages/msg_nope/star", headers=h)
    assert r.status_code == 404 and err(r)["message"] == "Message not found."
    # allowed in closed rooms
    assert client.post(f"{API}/messages/msg_seed1_0/star", headers=auth("lisa")).status_code == 200


# ---------- closures ----------

def test_listen_room_closes_when_everyone_submits(client, auth):
    r = close(client, auth("carol"), "room_seed8", "  Helpful  ")
    assert r.status_code == 200
    room = r.json()
    assert room["status"] == "active" and room["closures"]["u_carol"]["text"] == "Helpful"
    assert err(send(client, auth("carol"), "room_seed8"))["message"] == "You have submitted and left this chat."
    r = close(client, auth("carol"), "room_seed8")
    assert r.status_code == 403 and err(r)["message"] == "You have already submitted."
    room = close(client, auth("lisa"), "room_seed8", "").json()
    assert room["status"] == "closed" and room["closedAt"] is not None
    assert detail(client, auth("carol"), "room_seed8")["needsRating"] is True


def test_closure_requires_active_room(client, auth):
    r = close(client, auth("bob"), "room_seed9")
    assert r.status_code == 403 and err(r)["message"] == "This chat is not open."


def test_moderator_verdict_closes_room(client, auth):
    room_id = start_moderated(client, auth)
    assert close(client, auth("alice"), room_id).json()["status"] == "active"
    assert close(client, auth("bob"), room_id).json()["status"] == "active"  # members never close it
    assert close(client, auth("maya"), room_id, "Verdict").json()["status"] == "closed"


# ---------- mute ----------

def test_mute_unmute(client, auth):
    room_id = start_moderated(client, auth)
    url = f"{API}/rooms/{room_id}/members/u_bob/mute"
    r = client.put(url, headers=auth("alice"), json={"muted": True})
    assert r.status_code == 403 and err(r)["message"] == "Only the moderator can mute."
    r = client.put(url, headers=auth("maya"), json={"muted": True})
    assert r.status_code == 200 and r.json()["mutedIds"] == ["u_bob"]
    assert client.put(url, headers=auth("maya"), json={"muted": True}).json()["mutedIds"] == ["u_bob"]
    assert err(send(client, auth("bob"), room_id))["message"] == "You have been muted by the moderator."
    assert client.put(url, headers=auth("maya"), json={"muted": False}).json()["mutedIds"] == []
    assert send(client, auth("bob"), room_id).status_code == 201
    for target in ("u_maya", "u_carol"):
        r = client.put(f"{API}/rooms/{room_id}/members/{target}/mute", headers=auth("maya"),
                       json={"muted": True})
        assert r.status_code == 422 and err(r)["message"] == "Cannot mute this member."


# ---------- ratings ----------

def test_rating_rules(client, auth):
    url = f"{API}/rooms/room_seed8/ratings"
    for bad in (0, 6, 2.5, "5", None, True):
        r = client.post(url, headers=auth("carol"), json={"stars": bad})
        assert r.status_code == 422 and err(r)["message"] == "Choose between 1 and 5 stars."
    # stars validated before room access
    r = client.post(f"{API}/rooms/room_nope/ratings", headers=auth("carol"), json={"stars": 9})
    assert r.status_code == 422
    r = client.post(url, headers=auth("carol"), json={"stars": 5})
    assert r.status_code == 403 and err(r)["message"] == "You can rate once the chat is closed."

    close(client, auth("carol"), "room_seed8")
    close(client, auth("lisa"), "room_seed8")
    r = client.post(url, headers=auth("lisa"), json={"stars": 5})
    assert r.status_code == 403 and err(r)["message"] == "Providers do not rate themselves."
    r = client.post(url, headers=auth("carol"), json={"stars": 4, "feedback": "  Kind  "})
    assert r.status_code == 201
    assert r.json()["ratings"][-1] | {"at": 0} == {"byId": "u_carol", "stars": 4, "feedback": "Kind", "at": 0}
    r = client.post(url, headers=auth("carol"), json={"stars": 4})
    assert r.status_code == 403 and err(r)["message"] == "You have already rated."
    assert detail(client, auth("carol"), "room_seed8")["needsRating"] is False


# ---------- summary ----------

def test_summary_listen(client, auth):
    s = client.get(f"{API}/rooms/room_seed1/summary", headers=auth("alice")).json()
    assert [m["id"] for m in s["starred"]] == ["msg_seed1_2", "msg_seed1_4"]
    assert s["starred"][0]["sender"]["id"] == "u_alice"
    assert [(c["user"]["id"], c["text"]) for c in s["comments"]] == [
        ("u_alice", "Felt lighter after talking it through.")]
    assert s["observation"]["text"] == "Alice benefits from breaking work into weekly lists."
    assert s["verdict"] is None
    assert s["provider"]["id"] == "u_lisa"


def test_summary_moderate(client, auth):
    s = client.get(f"{API}/rooms/room_seed5/summary", headers=auth("bob")).json()
    assert len(s["starred"]) == 3
    assert {c["user"]["id"] for c in s["comments"]} == {"u_alice", "u_bob"}
    assert s["observation"] is None
    assert s["verdict"] == {
        "user": s["provider"],
        "text": "Both agree to list contributions in shared reviews going forward.",
    }

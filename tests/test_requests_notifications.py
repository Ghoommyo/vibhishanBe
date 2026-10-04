from sqlalchemy import func, select

from app.db import models as m

API = "/api/v1"


def err(r):
    return r.json()["error"]


def notes(client, h):
    return client.get(f"{API}/notifications", headers=h).json()


def unread(client, h):
    return client.get(f"{API}/notifications/unread-count", headers=h).json()["count"]


def latest_request_id(client, h):
    return notes(client, h)[0]["requestId"]


# ---------- listen ----------

def test_listen_request_creates_room_and_notifications(client, auth):
    r = client.post(f"{API}/requests/listen", headers=auth("alice"),
                    json={"providerIds": ["u_leo", "u_lisa"]})
    assert r.status_code == 201
    assert r.json() == {"providerNames": ["Leo Fernandes", "Lisa Kapoor"], "participantNames": []}

    leo = notes(client, auth("leo"))[0]
    assert leo["kind"] == "request_received" and not leo["read"]
    assert leo["text"] == "Alice Sharma requested a listening session."
    assert leo["actionable"] is True
    assert leo["request"]["approvals"] == {"u_leo": "pending"}
    assert leo["request"]["participantIds"] == []
    assert leo["requester"]["id"] == "u_alice" and leo["provider"]["id"] == "u_leo"

    sent = [n["text"] for n in notes(client, auth("alice")) if n["kind"] == "request_sent"]
    assert "You sent a listening request to Leo Fernandes." in sent
    assert "You sent a listening request to Lisa Kapoor." in sent


def test_listen_validation_is_all_or_nothing(client, auth, db):
    before = db.scalar(select(func.count()).select_from(m.ServiceRequest))
    h = auth("alice")
    r = client.post(f"{API}/requests/listen", headers=h, json={"providerIds": []})
    assert r.status_code == 422 and err(r)["message"] == "Select at least one listener."
    r = client.post(f"{API}/requests/listen", headers=h, json={"providerIds": ["u_leo", "u_maya"]})
    assert r.status_code == 422 and err(r)["message"] == "Maya Iyer is not a listener."
    r = client.post(f"{API}/requests/listen", headers=h, json={"providerIds": ["u_leo", "u_x"]})
    assert r.status_code == 404 and err(r)["message"] == "User not found."
    db.rollback()
    assert db.scalar(select(func.count()).select_from(m.ServiceRequest)) == before


# ---------- moderate ----------

def test_moderate_request_notifies_participants_not_moderator(client, auth):
    r = client.post(f"{API}/requests/moderate", headers=auth("alice"), json={
        "providerId": "u_maya", "participantIds": ["u_bob", "u_carol", "u_bob", "u_alice"],
    })
    assert r.status_code == 201
    assert r.json() == {"providerNames": ["Maya Iyer"], "participantNames": ["Bob Mehta", "Carol Dsouza"]}
    bob = notes(client, auth("bob"))[0]
    assert bob["text"] == "Alice Sharma invited you to a session moderated by Maya Iyer."
    assert bob["request"]["participantIds"] == ["u_bob", "u_carol"]
    assert notes(client, auth("alice"))[0]["text"] == (
        "You sent a moderation request to Maya Iyer with Bob Mehta and Carol Dsouza.")
    assert notes(client, auth("maya")) == []


def test_moderate_validation(client, auth):
    h = auth("alice")
    r = client.post(f"{API}/requests/moderate", headers=h,
                    json={"providerId": "u_maya", "participantIds": ["u_alice"]})
    assert r.status_code == 422 and err(r)["message"] == "Add at least one participant."
    r = client.post(f"{API}/requests/moderate", headers=h,
                    json={"providerId": "u_lisa", "participantIds": ["u_bob"]})
    assert err(r)["message"] == "Lisa Kapoor is not a moderator."
    r = client.post(f"{API}/requests/moderate", headers=h,
                    json={"providerId": "u_maya", "participantIds": ["u_leo"]})
    assert err(r)["message"] == "Leo Fernandes can't be added as a participant."


# ---------- respond ----------

def test_moderate_flow(client, auth):
    client.post(f"{API}/requests/moderate", headers=auth("alice"),
                json={"providerId": "u_maya", "participantIds": ["u_bob", "u_carol"]})
    req_id = latest_request_id(client, auth("bob"))

    r = client.post(f"{API}/requests/{req_id}/respond", headers=auth("maya"), json={"accept": True})
    assert r.status_code == 403 and err(r)["message"] == "Waiting for all participants to accept first."

    r = client.post(f"{API}/requests/{req_id}/respond", headers=auth("bob"), json={"accept": True})
    assert r.status_code == 200 and r.json()["status"] == "pending"
    assert r.json()["approvals"]["u_bob"] == "accepted"
    assert notes(client, auth("alice"))[0]["text"] == "Bob Mehta accepted your invitation."
    assert notes(client, auth("maya")) == []

    r = client.post(f"{API}/requests/{req_id}/respond", headers=auth("bob"), json={"accept": True})
    assert r.status_code == 403 and err(r)["message"] == "You have already responded."

    client.post(f"{API}/requests/{req_id}/respond", headers=auth("carol"), json={"accept": True})
    maya = notes(client, auth("maya"))
    assert len(maya) == 1 and maya[0]["actionable"]
    assert maya[0]["text"] == "Alice Sharma requested a moderated session with Bob Mehta and Carol Dsouza."

    r = client.post(f"{API}/requests/{req_id}/respond", headers=auth("maya"), json={"accept": True})
    assert r.json()["status"] == "accepted"
    texts = [n["text"] for n in notes(client, auth("bob"))]
    assert "Maya Iyer accepted. The chatroom is now open." in texts
    assert notes(client, auth("maya"))[0]["actionable"] is False

    r = client.post(f"{API}/requests/{req_id}/respond", headers=auth("maya"), json={"accept": True})
    assert r.status_code == 409 and err(r) == {
        "code": "closed", "message": "This request has already been resolved."}


def test_reject_and_missing(client, auth, db):
    r = client.post(f"{API}/requests/req_seed9/respond", headers=auth("leo"), json={"accept": False})
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    assert db.get(m.Room, "room_seed9").status == "rejected"
    assert notes(client, auth("bob"))[0]["text"] == "Leo Fernandes declined the request."

    r = client.post(f"{API}/requests/req_nope/respond", headers=auth("leo"), json={"accept": True})
    assert r.status_code == 404 and err(r)["message"] == "Request not found."


def test_non_approver_cannot_respond(client, auth):
    r = client.post(f"{API}/requests/req_seed9/respond", headers=auth("bob"), json={"accept": True})
    assert r.status_code == 403 and err(r)["message"] == "You have already responded."


# ---------- notifications ----------

def test_seed_notifications_and_read_all(client, auth):
    h = auth("leo")
    items = notes(client, h)
    assert [n["id"] for n in items] == ["ntf_seed1"]
    assert items[0]["actionable"] is True
    assert unread(client, h) == 1
    assert client.post(f"{API}/notifications/read-all", headers=h).status_code == 204
    assert unread(client, h) == 0
    assert unread(client, auth("bob")) == 0  # ntf_seed2 is seeded as read


def test_notify_requests_off_arrives_read(client, auth):
    client.patch(f"{API}/users/me/settings", headers=auth("bob"), json={"notifyRequests": False})
    client.post(f"{API}/requests/req_seed9/respond", headers=auth("leo"), json={"accept": True})
    update = notes(client, auth("bob"))[0]
    assert update["kind"] == "request_update" and update["read"] is True
    assert unread(client, auth("bob")) == 0

API = "/api/v1"


def err(r):
    return r.json()["error"]


# ---------- auth ----------

def test_signup_creates_user_and_logs_in(client):
    r = client.post(f"{API}/auth/signup", json={
        "username": " dave ", "email": "Dave@Example.com", "password": "secret123", "role": "user",
    })
    assert r.status_code == 201
    body = r.json()
    user = body["user"]
    assert user["username"] == "dave"
    assert user["email"] == "dave@example.com"
    assert user["profile"] == {"name": "dave", "phone": "", "bio": "", "expertise": []}
    assert user["settings"] == {"notifyRequests": True, "showMessagePreviews": True, "available": True}
    assert isinstance(user["createdAt"], int)
    assert "password" not in str(body).lower()
    me = client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {body['token']}"})
    assert me.status_code == 200 and me.json()["id"] == user["id"]


def test_signup_conflicts_and_validation(client):
    base = {"username": "dave", "email": "dave@x.com", "password": "secret123", "role": "user"}
    r = client.post(f"{API}/auth/signup", json={**base, "username": "ALICE"})
    assert r.status_code == 409 and err(r) == {
        "code": "username_taken", "message": "That username is already taken."}
    r = client.post(f"{API}/auth/signup", json={**base, "email": "Alice@Vibishan.app"})
    assert r.status_code == 409 and err(r)["code"] == "email_taken"
    assert err(r)["message"] == "An account with that email already exists."
    r = client.post(f"{API}/auth/signup", json={**base, "email": "nope"})
    assert r.status_code == 422 and err(r) == {"code": "invalid_email", "message": "Enter a valid email."}
    r = client.post(f"{API}/auth/signup", json={**base, "password": "short"})
    assert r.status_code == 422 and err(r)["code"] == "validation"
    r = client.post(f"{API}/auth/signup", json={"username": "x"})
    assert r.status_code == 422 and err(r)["code"] == "validation"


def test_login_errors(client):
    r = client.post(f"{API}/auth/login", json={"username": "alice", "password": "bad", "role": "user"})
    assert r.status_code == 401 and err(r) == {
        "code": "invalid_credentials", "message": "Incorrect username or password."}
    r = client.post(f"{API}/auth/login",
                    json={"username": " Alice ", "password": "password123", "role": "listener"})
    assert r.status_code == 403 and err(r) == {
        "code": "wrong_role", "message": "This account is registered as a User."}


def test_auth_required(client):
    for headers in ({}, {"Authorization": "Bearer garbage"}):
        r = client.get(f"{API}/auth/me", headers=headers)
        assert r.status_code == 401 and err(r) == {
            "code": "unauthorized", "message": "Please log in again."}


def test_logout(client, auth):
    assert client.post(f"{API}/auth/logout", headers=auth("alice")).status_code == 204


# ---------- users ----------

def test_users_me_includes_rating(client, auth):
    r = client.get(f"{API}/users/me", headers=auth("lisa"))
    assert r.status_code == 200
    rating = r.json()["rating"]
    assert rating["count"] == 3 and round(rating["average"], 2) == 4.67
    r = client.get(f"{API}/users/me", headers=auth("alice"))
    assert r.json()["rating"] == {"average": None, "count": 0}


def test_update_profile(client, auth):
    h = auth("alice")
    r = client.patch(f"{API}/users/me/profile", headers=h,
                     json={"bio": "New bio", "email": " New@X.com "})
    assert r.status_code == 200
    assert r.json()["profile"]["bio"] == "New bio"
    assert r.json()["profile"]["name"] == "Alice Sharma"  # untouched
    assert r.json()["email"] == "new@x.com"
    r = client.patch(f"{API}/users/me/profile", headers=h, json={"email": "bob@vibishan.app"})
    assert r.status_code == 409 and err(r)["code"] == "email_taken"
    r = client.patch(f"{API}/users/me/profile", headers=h, json={"email": "bad"})
    assert r.status_code == 422 and err(r)["code"] == "invalid_email"


def test_update_settings_and_availability(client, auth):
    r = client.patch(f"{API}/users/me/settings", headers=auth("leo"), json={"available": False})
    assert r.status_code == 200
    assert r.json()["settings"] == {"notifyRequests": True, "showMessagePreviews": True, "available": False}
    r = client.get(f"{API}/providers", params={"role": "listener"}, headers=auth("alice"))
    assert [p["id"] for p in r.json()] == ["u_lisa"]


def test_get_user(client, auth):
    r = client.get(f"{API}/users/u_bob", headers=auth("alice"))
    assert r.status_code == 200 and r.json()["username"] == "bob"
    r = client.get(f"{API}/users/u_nobody", headers=auth("alice"))
    assert r.status_code == 404 and err(r) == {"code": "not_found", "message": "User not found."}


def test_list_providers(client, auth):
    h = auth("alice")
    r = client.get(f"{API}/providers", params={"role": "listener"}, headers=h)
    assert r.status_code == 200
    providers = {p["id"]: p for p in r.json()}
    assert set(providers) == {"u_lisa", "u_leo"}
    assert providers["u_lisa"]["rating"]["count"] == 3
    assert round(providers["u_lisa"]["rating"]["average"], 2) == 4.67
    assert providers["u_leo"]["rating"] == {"average": 4.0, "count": 1}
    r = client.get(f"{API}/providers", params={"role": "moderator", "q": "IYER"}, headers=h)
    assert [p["id"] for p in r.json()] == ["u_maya"]
    r = client.get(f"{API}/providers", params={"role": "moderator", "q": "  "}, headers=h)
    assert len(r.json()) == 2
    r = client.get(f"{API}/providers", params={"role": "user"}, headers=h)
    assert r.status_code == 422 and err(r)["code"] == "validation"


def test_search_users_excludes_caller_and_providers(client, auth):
    r = client.get(f"{API}/users/search", headers=auth("alice"))
    assert {u["id"] for u in r.json()} == {"u_bob", "u_carol"}
    r = client.get(f"{API}/users/search", params={"q": "mehta"}, headers=auth("alice"))
    assert [u["id"] for u in r.json()] == ["u_bob"]

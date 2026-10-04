from app.core.utils import join_names


def test_health_ok(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_unknown_route_uses_error_envelope(client):
    r = client.get("/api/v1/does-not-exist")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_join_names():
    assert join_names(["Bob"]) == "Bob"
    assert join_names(["Bob", "Carol"]) == "Bob and Carol"
    assert join_names(["Bob", "Carol", "Dan"]) == "Bob, Carol and Dan"

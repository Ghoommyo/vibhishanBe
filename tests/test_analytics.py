import re
from datetime import datetime, timedelta, timezone

API = "/api/v1"


def stats(client, h, **params):
    r = client.get(f"{API}/analytics/provider", headers=h, params=params)
    assert r.status_code == 200
    return r.json()


def test_listener_stats_from_seed(client, auth):
    s = stats(client, auth("lisa"))
    assert s["listeningDone"] == 3 and s["moderationDone"] == 0 and s["activeSessions"] == 1
    assert s["ratingCount"] == 3 and round(s["averageRating"], 2) == 4.67
    assert s["ratingDistribution"] == [0, 0, 0, 1, 2]
    assert [w["value"] for w in s["weekly"]] == [1, 0, 1, 0, 0, 0, 1, 0]
    assert [f["text"] for f in s["feedback"]] == [
        "Always a good conversation.",
        "Helpful questions, felt heard.",
        "Lisa was calm and really listened.",
    ]
    assert s["feedback"][1]["by"]["id"] == "u_bob"


def test_moderator_stats(client, auth):
    s = stats(client, auth("maya"))
    assert s["moderationDone"] == 2 and s["listeningDone"] == 0
    assert s["ratingDistribution"] == [0, 0, 0, 1, 2]


def test_plain_user_gets_zeros(client, auth):
    s = stats(client, auth("alice"))
    assert s["listeningDone"] == s["moderationDone"] == s["activeSessions"] == s["ratingCount"] == 0
    assert s["averageRating"] is None and s["ratingDistribution"] == [0] * 5 and s["feedback"] == []
    assert sum(w["value"] for w in s["weekly"]) == 0


def test_weekly_buckets_and_tz_labels(client, auth):
    s = stats(client, auth("lisa"), tzOffset=-330)
    weekly = s["weekly"]
    assert len(weekly) == 8 and weekly[-1]["label"] == "Now"
    for a, b in zip(weekly, weekly[1:]):
        assert a["end"] == b["start"] and b["end"] - b["start"] == 7 * 24 * 3600 * 1000
    for w in weekly[:-1]:
        local = datetime.fromtimestamp((w["start"] + 1) / 1000, tz=timezone.utc) + timedelta(minutes=330)
        assert w["label"] == f"{local.day}/{local.month}"
        assert re.fullmatch(r"\d{1,2}/\d{1,2}", w["label"])

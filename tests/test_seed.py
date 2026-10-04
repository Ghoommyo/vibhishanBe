from sqlalchemy import func, select

from app.db import models as m


def count(db, model):
    return db.scalar(select(func.count()).select_from(model))


def test_seed_row_counts(db):
    assert count(db, m.User) == 7
    assert count(db, m.ServiceRequest) == 9
    assert count(db, m.Room) == 9
    assert count(db, m.Message) == 26
    assert count(db, m.MessageStar) == 13
    assert count(db, m.RoomClosure) == 15
    assert count(db, m.RoomRating) == 9
    assert count(db, m.Notification) == 2


def test_seed_room_states(db):
    assert db.get(m.Room, "room_seed8").status == "active"
    room9 = db.get(m.Room, "room_seed9")
    assert room9.status == "pending" and room9.closed_at is None
    assert db.get(m.ServiceRequest, "req_seed9").status == "pending"
    members = db.scalars(
        select(m.RoomMember.user_id).where(m.RoomMember.room_id == "room_seed5")
        .order_by(m.RoomMember.position)
    ).all()
    assert members == ["u_alice", "u_bob", "u_maya"]


def test_dev_reset_restores_seed(client, db):
    db.delete(db.get(m.Notification, "ntf_seed1"))
    db.commit()
    assert count(db, m.Notification) == 1
    db.rollback()  # release locks so the reset's TRUNCATE isn't blocked
    r = client.post("/api/v1/dev/reset")
    assert r.status_code == 204
    db.expire_all()
    assert count(db, m.Notification) == 2

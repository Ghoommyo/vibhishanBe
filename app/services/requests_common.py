"""Assembling the nested ServiceRequest shape from the normalized tables."""

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.utils import to_ms
from app.db.models import RequestApproval, RequestParticipant, ServiceRequest
from app.schemas.requests import ServiceRequestOut


def serialize_requests(db: Session, reqs) -> dict[str, ServiceRequestOut]:
    reqs = list(reqs)
    ids = [r.id for r in reqs]
    if not ids:
        return {}
    participants: dict[str, list[str]] = defaultdict(list)
    for p in db.scalars(
        select(RequestParticipant)
        .where(RequestParticipant.request_id.in_(ids))
        .order_by(RequestParticipant.request_id, RequestParticipant.position)
    ):
        participants[p.request_id].append(p.user_id)
    approvals: dict[str, dict[str, str]] = defaultdict(dict)
    for a in db.scalars(select(RequestApproval).where(RequestApproval.request_id.in_(ids))):
        approvals[a.request_id][a.user_id] = a.state

    return {
        r.id: ServiceRequestOut(
            id=r.id, kind=r.kind, requester_id=r.requester_id, provider_id=r.provider_id,
            participant_ids=participants[r.id], approvals=approvals[r.id], status=r.status,
            room_id=r.room_id, created_at=to_ms(r.created_at),
        )
        for r in reqs
    }


def serialize_request(db: Session, req: ServiceRequest) -> ServiceRequestOut:
    return serialize_requests(db, [req])[req.id]

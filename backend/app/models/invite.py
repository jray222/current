from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from app.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


class Invite(Base):
    """
    An invite code for signing up on an invite-only instance. Only the code's
    SHA-256 hash is stored, so the code itself is shown once, when created.

    household_id None: the invitee gets a new household of their own (created
    by the instance owner). Set: the invitee joins that household as a member
    (created by one of its admins).
    """
    __tablename__ = "invites"

    id = Column(Integer, primary_key=True, index=True)
    code_hash = Column(String(64), unique=True, nullable=False, index=True)
    household_id = Column(Integer, ForeignKey("households.id"), nullable=True, index=True)
    grants_admin = Column(Boolean, default=False, nullable=False)
    note = Column(String(100), nullable=True)
    # Plain ids (no FK) so users <-> invites don't form a foreign-key cycle.
    created_by_id = Column(Integer, nullable=True, index=True)
    max_uses = Column(Integer, nullable=False, default=1)
    use_count = Column(Integer, nullable=False, default=0)
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)
    last_used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_utcnow)

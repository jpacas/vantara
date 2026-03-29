import math
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from db.models import (
    Blocker,
    Checkin,
    Commitment,
    Delegation,
    Evidence,
    Project,
    SessionLocal,
    SystemLog,
    UserState,
)


# ---------------------------------------------------------------------------
# User state
# ---------------------------------------------------------------------------


def get_user_state(telegram_id: int) -> UserState | None:
    with SessionLocal() as session:
        result = session.execute(
            select(UserState).where(UserState.telegram_id == telegram_id)
        ).scalar_one_or_none()
        if result is not None:
            session.refresh(result)
        return result


def create_user_state(telegram_id: int) -> UserState:
    with SessionLocal() as session:
        user = UserState(telegram_id=telegram_id)
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


def update_conversation_state(telegram_id: int, new_state: str) -> None:
    with SessionLocal() as session:
        user = session.execute(
            select(UserState).where(UserState.telegram_id == telegram_id)
        ).scalar_one()
        user.conversation_state = new_state
        session.commit()


def set_pause(telegram_id: int, until_date: datetime | None) -> None:
    with SessionLocal() as session:
        user = session.execute(
            select(UserState).where(UserState.telegram_id == telegram_id)
        ).scalar_one()
        user.pause_until = until_date
        session.commit()


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


def get_active_projects(user_id: int) -> list[Project]:
    with SessionLocal() as session:
        results = session.execute(
            select(Project)
            .where(Project.user_id == user_id, Project.is_active == True)
            .order_by(Project.priority.asc())
        ).scalars().all()
        for p in results:
            session.refresh(p)
        return list(results)


def get_project_by_id(project_id: int) -> Project | None:
    with SessionLocal() as session:
        result = session.execute(
            select(Project).where(Project.id == project_id)
        ).scalar_one_or_none()
        if result is not None:
            session.refresh(result)
        return result


def create_project(
    user_id: int,
    name: str,
    priority: int,
    why_it_matters: str | None = None,
    objective: str | None = None,
    current_state: str | None = None,
    next_milestone: str | None = None,
    next_action: str | None = None,
    acceptable_evidence: str | None = None,
) -> Project:
    with SessionLocal() as session:
        project = Project(
            user_id=user_id,
            name=name,
            priority=priority,
            why_it_matters=why_it_matters,
            objective=objective,
            current_state=current_state,
            next_milestone=next_milestone,
            next_action=next_action,
            acceptable_evidence=acceptable_evidence,
        )
        session.add(project)
        session.commit()
        session.refresh(project)
        return project


def update_project(project_id: int, **fields) -> None:
    """Update project fields. E.g. update_project(id, current_state='...', progress_pct=50)"""
    with SessionLocal() as session:
        project = session.get(Project, project_id)
        if project:
            for key, value in fields.items():
                setattr(project, key, value)
            session.commit()


# ---------------------------------------------------------------------------
# Check-ins
# ---------------------------------------------------------------------------


def get_todays_checkin(user_id: int, checkin_type: str) -> Checkin | None:
    with SessionLocal() as session:
        result = session.execute(
            select(Checkin).where(
                Checkin.user_id == user_id,
                Checkin.checkin_type == checkin_type,
                Checkin.date == date.today(),
            )
        ).scalar_one_or_none()
        if result is not None:
            session.refresh(result)
        return result


def create_checkin(user_id: int, checkin_type: str) -> Checkin | None:
    """Returns None if a checkin already exists for (user_id, date, checkin_type)."""
    with SessionLocal() as session:
        checkin = Checkin(
            user_id=user_id,
            checkin_type=checkin_type,
            date=date.today(),
        )
        session.add(checkin)
        try:
            session.commit()
            session.refresh(checkin)
            return checkin
        except IntegrityError:
            session.rollback()
            return None


def update_checkin(checkin_id: int, **fields) -> None:
    """Update any fields on a checkin. E.g. update_checkin(id, user_response='...', status='responded')"""
    with SessionLocal() as session:
        checkin = session.get(Checkin, checkin_id)
        if checkin:
            for key, value in fields.items():
                setattr(checkin, key, value)
            session.commit()


# ---------------------------------------------------------------------------
# Commitments
# ---------------------------------------------------------------------------


def get_open_commitments(user_id: int) -> list[Commitment]:
    with SessionLocal() as session:
        results = session.execute(
            select(Commitment).where(
                Commitment.user_id == user_id,
                Commitment.status == "open",
            )
        ).scalars().all()
        for r in results:
            session.refresh(r)
        return list(results)


def create_commitment(
    user_id: int,
    project_id: int,
    checkin_id: int,
    description: str,
    due_date=None,
) -> Commitment:
    with SessionLocal() as session:
        commitment = Commitment(
            user_id=user_id,
            project_id=project_id,
            checkin_id=checkin_id,
            description=description,
            due_date=due_date,
        )
        session.add(commitment)
        session.commit()
        session.refresh(commitment)
        return commitment


def fulfill_commitment(commitment_id: int) -> None:
    with SessionLocal() as session:
        commitment = session.get(Commitment, commitment_id)
        if commitment:
            commitment.status = 'fulfilled'
            session.commit()


def break_commitment(commitment_id: int) -> None:
    with SessionLocal() as session:
        commitment = session.get(Commitment, commitment_id)
        if commitment:
            commitment.status = 'broken'
            session.commit()


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------


def get_recent_evidence(user_id: int, days: int = 7) -> list[Evidence]:
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
    with SessionLocal() as session:
        results = session.execute(
            select(Evidence).where(
                Evidence.user_id == user_id,
                Evidence.recorded_at >= cutoff,
            )
        ).scalars().all()
        for r in results:
            session.refresh(r)
        return list(results)


def record_evidence(
    user_id: int,
    project_id: int,
    description: str,
    evidence_type: str = "text",
    commitment_id: int | None = None,
) -> Evidence:
    with SessionLocal() as session:
        evidence = Evidence(
            user_id=user_id,
            project_id=project_id,
            description=description,
            evidence_type=evidence_type,
            commitment_id=commitment_id,
        )
        session.add(evidence)
        session.commit()
        session.refresh(evidence)
        return evidence


def get_days_since_movement(project_id: int) -> int | None:
    """Returns days since last evidence for this project, or None if no evidence exists."""
    with SessionLocal() as session:
        latest = session.execute(
            select(Evidence.recorded_at)
            .where(Evidence.project_id == project_id)
            .order_by(Evidence.recorded_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if latest is None:
            return None
        delta = datetime.now(tz=timezone.utc) - latest
        return math.ceil(delta.total_seconds() / 86400)


# ---------------------------------------------------------------------------
# Blockers
# ---------------------------------------------------------------------------


def get_open_blockers(user_id: int) -> list[Blocker]:
    with SessionLocal() as session:
        results = session.execute(
            select(Blocker).where(
                Blocker.user_id == user_id,
                Blocker.is_resolved == False,
            )
        ).scalars().all()
        for r in results:
            session.refresh(r)
        return list(results)


def create_blocker(user_id: int, project_id: int, description: str) -> Blocker:
    with SessionLocal() as session:
        blocker = Blocker(user_id=user_id, project_id=project_id, description=description)
        session.add(blocker)
        session.commit()
        session.refresh(blocker)
        return blocker


def resolve_blocker(blocker_id: int) -> None:
    with SessionLocal() as session:
        blocker = session.execute(
            select(Blocker).where(Blocker.id == blocker_id)
        ).scalar_one()
        blocker.is_resolved = True
        session.commit()


# ---------------------------------------------------------------------------
# Delegations
# ---------------------------------------------------------------------------


def get_open_delegations(user_id: int) -> list[Delegation]:
    with SessionLocal() as session:
        results = session.execute(
            select(Delegation).where(
                Delegation.user_id == user_id,
                Delegation.status == "pending",
            )
        ).scalars().all()
        for r in results:
            session.refresh(r)
        return list(results)


def create_delegation(
    user_id: int,
    project_id: int,
    description: str,
    delegated_to: str | None = None,
    follow_up_date=None,
) -> Delegation:
    with SessionLocal() as session:
        delegation = Delegation(
            user_id=user_id,
            project_id=project_id,
            description=description,
            delegated_to=delegated_to,
            follow_up_date=follow_up_date,
        )
        session.add(delegation)
        session.commit()
        session.refresh(delegation)
        return delegation


# ---------------------------------------------------------------------------
# System logs
# ---------------------------------------------------------------------------


def log_event(user_id: int | None, event_type: str, payload: dict) -> None:
    with SessionLocal() as session:
        log = SystemLog(user_id=user_id, event_type=event_type, payload=payload)
        session.add(log)
        session.commit()

"""
FastAPI application entry point.

Current routes
--------------
GET  /          — health check
POST /events    — submit a new event (auth + validation + DB write)
GET  /events/{id} — fetch event status
"""

from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Event
from app.schemas import EventCreate, EventResponse

app = FastAPI(
    title="Alerty — Event Processing Platform",
    description=(
        "A backend service that receives events, stores them safely, "
        "and notifies external systems via webhooks. "
        "Same core pattern used by Stripe, Segment, and Twilio."
    ),
    version="0.1.0",
)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/", tags=["Health"])
def root():
    """Quick liveness check — confirms the API is reachable."""
    return {"status": "ok", "service": "Alerty Event Processing Platform"}


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

@app.post(
    "/events",
    response_model=EventResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Events"],
    summary="Submit a new event",
)
def create_event(
    body: EventCreate,
    db: Session = Depends(get_db),
):
    """
    Accept an event from a client application.

    - Validates the request body (Pydantic).
    - Persists the event to PostgreSQL.
    - Returns `409 Conflict` if the same `idempotency_key` was already submitted
      by the same organisation (enforced by the database, not just application code).

    **Note:** authentication and queueing will be wired in later steps.
    """
    # Temporary: use a fixed placeholder org/api_key UUID until auth is in place.
    # Step 3 will replace this with real API-key verification.
    import uuid
    PLACEHOLDER_ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
    PLACEHOLDER_KEY_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")

    event = Event(
        organization_id=PLACEHOLDER_ORG_ID,
        api_key_id=PLACEHOLDER_KEY_ID,
        idempotency_key=body.idempotency_key,
        event_type=body.event_type,
        payload=body.payload,
        status="received",
    )

    db.add(event)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An event with idempotency_key='{body.idempotency_key}' already exists.",
        )

    db.refresh(event)
    return event


@app.get(
    "/events/{event_id}",
    response_model=EventResponse,
    tags=["Events"],
    summary="Get event status",
)
def get_event(event_id: UUID, db: Session = Depends(get_db)):
    """
    Fetch a previously submitted event by its ID.

    Returns `404 Not Found` if the ID doesn't exist.
    """
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Event {event_id} not found.",
        )
    return event
"""
Pydantic schemas for request body validation and response serialization.
These are separate from SQLAlchemy models — they describe what comes *in*
and what goes *out* over the HTTP API, not what's stored in the database.
"""

from typing import Any
from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Event schemas
# ---------------------------------------------------------------------------

class EventCreate(BaseModel):
    """Shape of the JSON body required to submit a new event."""
    event_type: str = Field(..., min_length=1, max_length=100, examples=["order_placed"])
    idempotency_key: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="A unique key per event — re-sending the same key is safe (idempotent).",
        examples=["order-12345"],
    )
    payload: dict[str, Any] = Field(
        ...,
        description="Arbitrary JSON payload describing what happened.",
        examples=[{"order_id": "12345", "customer_email": "jane@example.com", "total_amount": 49.99}],
    )


class EventResponse(BaseModel):
    """Shape of the response body returned after a successful event submission."""
    id: UUID
    event_type: str
    status: str
    received_at: datetime

    model_config = {"from_attributes": True}

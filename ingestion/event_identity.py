"""Utilities for identifying individual telemetry events."""

from uuid import uuid4


def create_event_id() -> str:
    """Return a unique identifier for one telemetry event."""
    return str(uuid4())

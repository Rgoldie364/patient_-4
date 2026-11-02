"""Ephemeral, staff-bound suggestions with retry-safe review reservations."""

import secrets
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass

from prs.errors import ConflictError
from prs.models import Category


@dataclass(frozen=True, slots=True)
class Suggestion:
    suggestion_id: str
    note_id: str
    user_id: str
    category: Category
    confidence: float
    category_version: int
    expires_at: float


class SuggestionStore:
    """Own suggestion expiry, review ownership, and concurrent reservation state."""

    def __init__(self, lifetime: float = 300, capacity: int = 256):
        self._lifetime = lifetime
        self._capacity = capacity
        self._pending: dict[str, Suggestion] = {}
        self._reserved: set[str] = set()
        self._lock = threading.Lock()

    def add(
        self, note_id, user_id, category, confidence, category_version
    ) -> Suggestion | None:
        now = time.monotonic()
        with self._lock:
            self._prune(now)
            if len(self._pending) >= self._capacity:
                return None
            suggestion = Suggestion(
                secrets.token_urlsafe(24),
                note_id,
                user_id,
                category,
                confidence,
                category_version,
                now + self._lifetime,
            )
            self._pending[suggestion.suggestion_id] = suggestion
            return suggestion

    @contextmanager
    def reserve(self, suggestion_id: str, note_id: str, user_id: str):
        """Consume only after successful review; release a failed review for retry.

        No lock is held during database work. Other attempts to review this same
        suggestion are rejected while reserved. The database category version
        independently prevents stale suggestions from overwriting newer decisions.
        """
        with self._lock:
            self._prune(time.monotonic())
            value = self._pending.get(suggestion_id)
            if not value or value.note_id != note_id or value.user_id != user_id:
                raise ConflictError(
                    "Suggestion expired or does not belong to this staff member and note. Request a new suggestion."
                )
            if suggestion_id in self._reserved:
                raise ConflictError("This suggestion is already being reviewed.")
            self._reserved.add(suggestion_id)
        success = False
        try:
            yield value
            success = True
        finally:
            with self._lock:
                self._reserved.discard(suggestion_id)
                if success:
                    self._pending.pop(suggestion_id, None)
                self._prune(time.monotonic())

    def _prune(self, now: float) -> None:
        self._pending = {
            key: value
            for key, value in self._pending.items()
            if value.expires_at > now or key in self._reserved
        }

    @property
    def pending_count(self) -> int:
        """Expose a count without exposing the mutable suggestion dictionary."""
        with self._lock:
            self._prune(time.monotonic())
            return len(self._pending)

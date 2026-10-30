"""Bounded optional inference and ephemeral suggestions requiring staff review."""

from dataclasses import dataclass
import math
from queue import Queue, Empty
import secrets
import threading
import time

from prs.errors import ConflictError
from prs.models import Category
from prs.ai_integration.providers import Prediction


@dataclass(frozen=True)
class Suggestion:
    suggestion_id: str
    note_id: str
    user_id: str
    category: Category
    confidence: float
    category_version: int
    expires_at: float


@dataclass(frozen=True)
class SuggestionResult:
    status: str
    suggestion: Suggestion | None = None


class CategorizationService:
    def __init__(self, provider, timeout=4.75, confidence_threshold=0.75):
        self.provider = provider
        self.timeout = min(max(timeout, 0.001), 4.75)
        self.confidence_threshold = confidence_threshold
        self._slots = threading.BoundedSemaphore(4)
        self._pending = {}
        self._lock = threading.Lock()

    def request(self, note_id, text, user_id, category_version):
        if not self._slots.acquire(blocking=False):
            return SuggestionResult("unavailable")
        result_queue = Queue(maxsize=1)

        def infer():
            try:
                result_queue.put(self.provider.suggest(text))
            except Exception:
                result_queue.put(None)
            finally:
                self._slots.release()

        # A socket timeout alone is not a wall-clock deadline. This bounded daemon
        # worker also handles stuck providers. Late results can never reach storage.
        threading.Thread(target=infer, daemon=True).start()
        try:
            prediction = result_queue.get(timeout=self.timeout)
        except Empty:
            return SuggestionResult("timeout")
        if (not isinstance(prediction, Prediction) or type(prediction.confidence) not in (float, int)
                or not math.isfinite(prediction.confidence) or not 0 <= prediction.confidence <= 1
                or type(prediction.uncertain) is not bool):
            return SuggestionResult("unavailable")
        if prediction.uncertain or prediction.category is None or prediction.confidence < self.confidence_threshold:
            return SuggestionResult("uncertain")
        if not isinstance(prediction.category, Category):
            return SuggestionResult("unavailable")
        now = time.monotonic()
        suggestion = Suggestion(secrets.token_urlsafe(24), note_id, user_id, prediction.category,
                                prediction.confidence, category_version, now + 300)
        with self._lock:
            self._pending = {k: v for k, v in self._pending.items() if v.expires_at > now}
            if len(self._pending) >= 256:
                return SuggestionResult("unavailable")
            self._pending[suggestion.suggestion_id] = suggestion
        return SuggestionResult("suggested", suggestion)

    def consume(self, suggestion_id, note_id, user_id):
        with self._lock:
            value = self._pending.get(suggestion_id)
            if (not value or value.note_id != note_id or value.user_id != user_id
                    or value.expires_at <= time.monotonic()):
                raise ConflictError("Suggestion expired or does not belong to this staff member and note. Request a new suggestion.")
            return self._pending.pop(suggestion_id)

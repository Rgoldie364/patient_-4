"""Bound optional inference independently of suggestion storage and review."""

import logging
import threading
from dataclasses import dataclass
from queue import Empty, Queue

from prs.ai_integration.errors import ProviderError
from prs.ai_integration.providers import CategorizationProvider, Prediction

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class InferenceResult:
    status: str
    prediction: Prediction | None = None


class InferenceRunner:
    """Limit worker capacity and waiting time; late results have no storage access."""

    def __init__(self, provider: CategorizationProvider, timeout: float = 4.75):
        self._provider = provider
        self._timeout = min(max(timeout, 0.001), 4.75)
        self._slots = threading.BoundedSemaphore(4)

    def predict(self, text: str) -> InferenceResult:
        if not self._slots.acquire(blocking=False):
            return InferenceResult("unavailable")
        results = Queue(maxsize=1)
        worker = threading.Thread(target=self._run, args=(text, results), daemon=True)
        try:
            worker.start()
        except RuntimeError:
            self._slots.release()
            logger.error("AI worker could not start")
            return InferenceResult("unavailable")
        try:
            return results.get(timeout=self._timeout)
        except Empty:
            return InferenceResult("timeout")

    def _run(self, text: str, results: Queue) -> None:
        try:
            results.put(InferenceResult("ok", self._provider.suggest(text)))
        except (ProviderError, OSError) as exc:
            # Do not log model output, note text, or exception messages containing it.
            logger.warning("AI provider unavailable (%s)", type(exc).__name__)
            results.put(InferenceResult("unavailable"))
        except Exception as exc:
            logger.error("Unexpected AI provider failure (%s)", type(exc).__name__)
            results.put(InferenceResult("unavailable"))
        finally:
            self._slots.release()

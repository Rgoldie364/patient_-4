"""Interpret optional predictions and create suggestions for explicit staff review."""

import logging
import math
from dataclasses import dataclass

from prs.ai_integration.inference import InferenceRunner
from prs.ai_integration.providers import CategorizationProvider, Prediction
from prs.ai_integration.suggestions import Suggestion, SuggestionStore
from prs.models import Category

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SuggestionResult:
    status: str
    suggestion: Suggestion | None = None


class CategorizationService:
    """Keep classification policy separate from worker execution and review state."""

    def __init__(
        self, provider: CategorizationProvider, timeout=4.75, confidence_threshold=0.75
    ):
        self._runner = InferenceRunner(provider, timeout)
        self._confidence_threshold = confidence_threshold
        self._suggestions = SuggestionStore()

    @property
    def suggestions(self) -> SuggestionStore:
        """Return the review interface, not its internal mutable state."""
        return self._suggestions

    def request(self, note_id, text, user_id, category_version) -> SuggestionResult:
        result = self._runner.predict(text)
        if result.status != "ok":
            return SuggestionResult(result.status)
        prediction = result.prediction
        if not self._valid(prediction):
            logger.warning("AI returned an invalid prediction object")
            return SuggestionResult("unavailable")
        if (
            prediction.uncertain
            or prediction.category is None
            or prediction.confidence < self._confidence_threshold
        ):
            return SuggestionResult("uncertain")
        suggestion = self._suggestions.add(
            note_id,
            user_id,
            prediction.category,
            prediction.confidence,
            category_version,
        )
        return (
            SuggestionResult("suggested", suggestion)
            if suggestion
            else SuggestionResult("unavailable")
        )

    @staticmethod
    def _valid(prediction) -> bool:
        return (
            isinstance(prediction, Prediction)
            and type(prediction.confidence) in (float, int)
            and math.isfinite(prediction.confidence)
            and 0 <= prediction.confidence <= 1
            and type(prediction.uncertain) is bool
            and (
                prediction.category is None or isinstance(prediction.category, Category)
            )
        )

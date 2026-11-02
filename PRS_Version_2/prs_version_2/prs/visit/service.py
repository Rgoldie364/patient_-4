"""Visit operations keep durable note saving independent from optional AI."""

from uuid import uuid4

from prs.errors import ValidationError
from prs.models import Category, VisitNote
from prs.validation import clean_text, utc_now, valid_date, version_number


class VisitService:
    """Authorize visit operations and coordinate patient, storage, and AI components."""

    def __init__(self, repository, patients, auth, categorizer):
        self.repository = repository
        self.patients = patients
        self.auth = auth
        self.categorizer = categorizer

    def add(self, token: str, patient_id: str, visit_date: str, text: str) -> VisitNote:
        user = self.auth.require(token, "note_write")
        self.patients.get(token, patient_id)
        note = VisitNote(
            note_id="VIS-" + uuid4().hex,
            patient_id=patient_id,
            visit_date=valid_date(visit_date, "Visit date"),
            text=clean_text(text, "Visit note", 10000, True),
            author_id=user.user_id,
            created_at=utc_now(),
            category=None,
            category_source=None,
            reviewed_by=None,
            reviewed_at=None,
            category_version=0,
        )
        # No AI call exists on this path. Commit before any separate request.
        return self.repository.add(note)

    def get(self, token: str, note_id: str) -> VisitNote:
        self.auth.require(token)
        return self.repository.get(note_id)

    def history(self, token: str, patient_id: str) -> list[VisitNote]:
        self.patients.get(token, patient_id)
        return self.repository.history(patient_id)

    def suggest(self, token, note_id):
        user = self.auth.require(token, "categorize")
        note = self.repository.get(note_id)
        result = self.categorizer.request(
            note.note_id, note.text, user.user_id, note.category_version
        )
        self.auth.require(token, "categorize")  # Recheck after the optional wait.
        return result

    def review(
        self, token: str, note_id: str, suggestion_id: str, decision: str
    ) -> VisitNote:
        """Persist a staff decision before the suggestion is finally consumed."""
        user = self.auth.require(token, "categorize")
        note = self.repository.get(note_id)
        if decision not in {"accept", "reject"}:
            raise ValidationError("Accept or reject the suggestion.")
        with self.categorizer.suggestions.reserve(
            suggestion_id, note_id, user.user_id
        ) as suggestion:
            if decision == "reject":
                self.repository.reject(note_id, user.user_id)
                return note
            return self.repository.categorize(
                note_id,
                suggestion.category.value,
                "ai_accepted",
                user.user_id,
                suggestion.category_version,
            )

    def manual_category(
        self, token: str, note_id: str, category: str, expected_version: int
    ) -> VisitNote:
        user = self.auth.require(token, "categorize")
        try:
            selected = Category(category)
        except ValueError as exc:
            raise ValidationError(
                "Choose one of the four permitted categories."
            ) from exc
        return self.repository.categorize(
            note_id,
            selected.value,
            "manual",
            user.user_id,
            version_number(expected_version),
        )

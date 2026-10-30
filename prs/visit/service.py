from uuid import uuid4

from prs.errors import ValidationError
from prs.models import Category, VisitNote
from prs.validation import clean_text, utc_now, valid_date, version_number


class VisitService:
    def __init__(self, repository, patients, auth, categorizer):
        self.repository = repository
        self.patients = patients
        self.auth = auth
        self.categorizer = categorizer

    def add(self, token, patient_id, visit_date, text):
        user = self.auth.require(token, "note_write")
        self.patients.get(token, patient_id)
        note = VisitNote("VIS-" + uuid4().hex, patient_id, valid_date(visit_date, "Visit date"),
                         clean_text(text, "Visit note", 10000, True), user.user_id, utc_now(),
                         None, None, None, None, 0)
        # No AI call exists on this path. Commit before any separate request.
        return self.repository.add(note)

    def get(self, token, note_id):
        self.auth.require(token)
        return self.repository.get(note_id)

    def history(self, token, patient_id):
        self.patients.get(token, patient_id)
        return self.repository.history(patient_id)

    def suggest(self, token, note_id):
        user = self.auth.require(token, "categorize")
        note = self.repository.get(note_id)
        result = self.categorizer.request(note.note_id, note.text, user.user_id, note.category_version)
        self.auth.require(token, "categorize")  # Recheck after the optional wait.
        return result

    def review(self, token, note_id, suggestion_id, decision):
        user = self.auth.require(token, "categorize")
        self.repository.get(note_id)
        if decision not in {"accept", "reject"}:
            raise ValidationError("Accept or reject the suggestion.")
        suggestion = self.categorizer.consume(suggestion_id, note_id, user.user_id)
        if decision == "reject":
            self.repository.reject(note_id, user.user_id)
            return self.repository.get(note_id)
        return self.repository.categorize(note_id, suggestion.category.value, "ai_accepted",
                                          user.user_id, suggestion.category_version)

    def manual_category(self, token, note_id, category, expected_version):
        user = self.auth.require(token, "categorize")
        try:
            selected = Category(category)
        except ValueError as exc:
            raise ValidationError("Choose one of the four permitted categories.") from exc
        return self.repository.categorize(note_id, selected.value, "manual", user.user_id,
                                          version_number(expected_version))

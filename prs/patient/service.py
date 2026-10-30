from dataclasses import asdict
from uuid import uuid4

from prs.errors import ValidationError
from prs.models import Patient
from prs.validation import patient_fields, utc_now, version_number


class PatientService:
    EDITABLE = frozenset({"name", "date_of_birth", "email", "phone", "address"})

    def __init__(self, repository, auth):
        self.repository = repository
        self.auth = auth

    def create(self, token, **fields):
        user = self.auth.require(token, "patient_write")
        self._check_fields(fields)
        values = patient_fields(fields)
        now = utc_now()
        patient = Patient("PAT-" + uuid4().hex, **values, created_at=now, updated_at=now, version=0)
        return self.repository.create(patient, user.user_id)

    def get(self, token, patient_id):
        self.auth.require(token)
        return self.repository.get(patient_id)

    def update(self, token, patient_id, expected_version, **changes):
        user = self.auth.require(token, "patient_write")
        self._check_fields(changes)
        existing = asdict(self.repository.get(patient_id))
        values = {key: existing[key] for key in self.EDITABLE}
        values.update(changes)
        values = patient_fields(values)
        return self.repository.update(patient_id, values, version_number(expected_version), user.user_id)

    def changes(self, token, patient_id):
        self.get(token, patient_id)
        return self.repository.changes(patient_id)

    def _check_fields(self, fields):
        if set(fields) - self.EDITABLE:
            raise ValidationError("Only name, date of birth, email, phone, and address may be changed. Patient ID is immutable.")

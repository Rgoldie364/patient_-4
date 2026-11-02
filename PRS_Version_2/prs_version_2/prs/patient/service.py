from dataclasses import asdict
from uuid import uuid4

from prs.errors import ConflictError, DuplicatePatientIDError, ValidationError
from prs.models import Patient
from prs.validation import patient_fields, utc_now, version_number


class PatientService:
    """Authorize and validate patient operations, delegating storage to a repository."""

    EDITABLE = frozenset({"name", "date_of_birth", "email", "phone", "address"})
    MAX_ID_ATTEMPTS = 5

    def __init__(self, repository, auth):
        self.repository = repository
        self.auth = auth

    def create(self, token: str, **fields) -> Patient:
        """Create one patient; retry only primary-key collisions, at most five times."""
        user = self.auth.require(token, "patient_write")
        self._check_fields(fields)
        values = patient_fields(fields)
        now = utc_now()
        for _ in range(self.MAX_ID_ATTEMPTS):
            patient = Patient(
                "PAT-" + uuid4().hex,
                **values,
                created_at=now,
                updated_at=now,
                version=0,
            )
            try:
                return self.repository.create(patient, user.user_id)
            except DuplicatePatientIDError:
                continue
        raise ConflictError("Could not allocate a unique Patient ID. Please retry.")

    def get(self, token: str, patient_id: str) -> Patient:
        self.auth.require(token)
        return self.repository.get(patient_id)

    def update(
        self, token: str, patient_id: str, expected_version: int, **changes
    ) -> Patient:
        user = self.auth.require(token, "patient_write")
        self._check_fields(changes)
        existing = asdict(self.repository.get(patient_id))
        values = {key: existing[key] for key in self.EDITABLE}
        values.update(changes)
        values = patient_fields(values)
        return self.repository.update(
            patient_id, values, version_number(expected_version), user.user_id
        )

    def changes(self, token: str, patient_id: str) -> list[dict]:
        self.get(token, patient_id)
        return self.repository.changes(patient_id)

    def _check_fields(self, fields: dict) -> None:
        if set(fields) - self.EDITABLE:
            raise ValidationError(
                "Only name, date of birth, email, phone, and address may be changed. Patient ID is immutable."
            )

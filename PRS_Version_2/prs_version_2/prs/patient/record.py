"""Coordinate the existing patient, visit-history, and audit reads for one screen."""

from dataclasses import dataclass

from prs.models import Patient, VisitNote


@dataclass(frozen=True, slots=True)
class PatientRecord:
    patient: Patient
    notes: tuple[VisitNote, ...]
    changes: tuple[dict, ...]


class PatientRecordService:
    """Read a patient once instead of repeating existence checks across UI calls."""

    def __init__(self, patient_repository, visit_repository, auth):
        self._patients = patient_repository
        self._visits = visit_repository
        self._auth = auth

    def get(self, token: str, patient_id: str) -> PatientRecord:
        self._auth.require(token, "read")
        patient = self._patients.get(patient_id)
        return PatientRecord(
            patient=patient,
            notes=tuple(self._visits.history(patient_id)),
            changes=tuple(self._patients.changes(patient_id)),
        )

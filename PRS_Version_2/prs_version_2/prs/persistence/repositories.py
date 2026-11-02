"""SQL stays inside repositories; services supply validated values and actors."""

import json
import sqlite3
from dataclasses import asdict

from prs.errors import ConflictError, DuplicatePatientIDError, NotFoundError
from prs.models import Patient, VisitNote
from prs.validation import utc_now


def audit(db, actor_id, action, entity_id, details):
    db.execute(
        "INSERT INTO audit_log(actor_id,action,entity_id,details,occurred_at) VALUES(?,?,?,?,?)",
        (actor_id, action, entity_id, json.dumps(details, sort_keys=True), utc_now()),
    )


class StaffRepository:
    """Persist staff accounts and optionally audit administrator-created accounts."""

    def __init__(self, database):
        self.database = database

    def add(self, user_id, username, password_hash, role, actor_id=None):
        try:
            with self.database.connect() as db:
                db.execute(
                    "INSERT INTO staff(user_id,username,password_hash,role) VALUES(?,?,?,?)",
                    (user_id, username, password_hash, role),
                )
                if actor_id is not None:
                    audit(
                        db,
                        actor_id,
                        "staff_created",
                        user_id,
                        {"username": username, "role": role},
                    )
        except sqlite3.IntegrityError as exc:
            if str(exc) == "UNIQUE constraint failed: staff.username":
                raise ConflictError("That staff username already exists.") from exc
            raise

    def by_username(self, username):
        with self.database.connect() as db:
            row = db.execute(
                "SELECT * FROM staff WHERE username = ?", (username,)
            ).fetchone()
            return dict(row) if row else None

    def by_id(self, user_id):
        with self.database.connect() as db:
            row = db.execute(
                "SELECT * FROM staff WHERE user_id = ?", (user_id,)
            ).fetchone()
            return dict(row) if row else None


class PatientRepository:
    """Persist patients, translating only patient-ID collisions into retryable errors."""

    def __init__(self, database):
        self.database = database

    def create(self, patient: Patient, actor_id: str):
        data = asdict(patient)
        try:
            with self.database.connect() as db:
                db.execute(
                    """INSERT INTO patients
                    (patient_id,name,date_of_birth,email,phone,address,created_at,updated_at,version)
                    VALUES(:patient_id,:name,:date_of_birth,:email,:phone,:address,:created_at,:updated_at,:version)""",
                    data,
                )
                audit(db, actor_id, "patient_created", patient.patient_id, data)
        except sqlite3.IntegrityError as exc:
            if str(exc) == "UNIQUE constraint failed: patients.patient_id":
                raise DuplicatePatientIDError("Patient ID already exists.") from exc
            raise
        return patient

    def get(self, patient_id: str) -> Patient:
        with self.database.connect() as db:
            row = db.execute(
                "SELECT * FROM patients WHERE patient_id = ?", (patient_id,)
            ).fetchone()
        if row is None:
            raise NotFoundError("Patient not found")
        return Patient(**dict(row))

    def update(self, patient_id, fields, expected_version, actor_id):
        with self.database.connect() as db:
            old = db.execute(
                "SELECT * FROM patients WHERE patient_id = ?", (patient_id,)
            ).fetchone()
            if old is None:
                raise NotFoundError("Patient not found")
            values = dict(
                fields,
                patient_id=patient_id,
                expected_version=expected_version,
                updated_at=utc_now(),
            )
            changed = db.execute(
                """UPDATE patients SET name=:name,date_of_birth=:date_of_birth,
                email=:email,phone=:phone,address=:address,updated_at=:updated_at,version=version+1
                WHERE patient_id=:patient_id AND version=:expected_version""",
                values,
            ).rowcount
            if not changed:
                raise ConflictError(
                    "Patient changed in another window. Reload before updating."
                )
            audit(
                db,
                actor_id,
                "patient_updated",
                patient_id,
                {
                    k: {"before": old[k], "after": v}
                    for k, v in fields.items()
                    if old[k] != v
                },
            )
            result = db.execute(
                "SELECT * FROM patients WHERE patient_id=?", (patient_id,)
            ).fetchone()
        return Patient(**dict(result))

    def changes(self, patient_id):
        with self.database.connect() as db:
            return [
                dict(row)
                for row in db.execute(
                    """SELECT a.*,s.username FROM audit_log a
                JOIN staff s ON a.actor_id=s.user_id WHERE entity_id=? ORDER BY event_id DESC""",
                    (patient_id,),
                )
            ]


class VisitRepository:
    """Persist immutable note content and atomic category/audit changes."""

    def __init__(self, database):
        self.database = database

    def add(self, note: VisitNote):
        with self.database.connect() as db:
            db.execute(
                """INSERT INTO visit_notes
                (note_id,patient_id,visit_date,text,author_id,created_at,category,category_source,
                 reviewed_by,reviewed_at,category_version)
                VALUES(:note_id,:patient_id,:visit_date,:text,:author_id,
                :created_at,:category,:category_source,:reviewed_by,:reviewed_at,:category_version)""",
                asdict(note),
            )
            audit(
                db,
                note.author_id,
                "note_created",
                note.note_id,
                {"patient_id": note.patient_id},
            )
        return note

    def get(self, note_id):
        with self.database.connect() as db:
            row = db.execute(
                "SELECT * FROM visit_notes WHERE note_id=?", (note_id,)
            ).fetchone()
        if row is None:
            raise NotFoundError("Visit note not found")
        return VisitNote(**dict(row))

    def history(self, patient_id):
        with self.database.connect() as db:
            return [
                VisitNote(**dict(row))
                for row in db.execute(
                    """SELECT * FROM visit_notes
                WHERE patient_id=? ORDER BY visit_date DESC,created_at DESC,note_id DESC""",
                    (patient_id,),
                )
            ]

    def categorize(self, note_id, category, source, actor_id, expected_version):
        with self.database.connect() as db:
            old = db.execute(
                "SELECT * FROM visit_notes WHERE note_id=?", (note_id,)
            ).fetchone()
            if old is None:
                raise NotFoundError("Visit note not found")
            changed = db.execute(
                """UPDATE visit_notes SET category=?,category_source=?,reviewed_by=?,
                reviewed_at=?,category_version=category_version+1 WHERE note_id=? AND category_version=?""",
                (category, source, actor_id, utc_now(), note_id, expected_version),
            ).rowcount
            if not changed:
                raise ConflictError(
                    "Category changed since this page or suggestion was loaded. Reload and review again."
                )
            audit(
                db,
                actor_id,
                "category_" + source,
                note_id,
                {"before": old["category"], "after": category},
            )
            updated = db.execute(
                "SELECT * FROM visit_notes WHERE note_id=?", (note_id,)
            ).fetchone()
        return VisitNote(**dict(updated))

    def reject(self, note_id, actor_id):
        with self.database.connect() as db:
            audit(db, actor_id, "suggestion_rejected", note_id, {})

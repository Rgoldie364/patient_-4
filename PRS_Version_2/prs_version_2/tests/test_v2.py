"""Version 2 regression cases for the requested fixes and retained boundaries."""

import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from prs.ai_integration.errors import ProviderUnavailableError
from prs.ai_integration.suggestions import SuggestionStore
from prs.errors import AuthorizationError, ConflictError, ValidationError
from prs.models import Category
from prs.ui.web import create_app
from tests.test_prs import TestProvider


class V2Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database_path = str(Path(self.temp.name) / "v2.sqlite3")
        self.provider = TestProvider()
        self.web = create_app(self.database_path, self.provider, testing=True)
        self.app = self.web.extensions["prs"]
        self.app.auth.provision_staff("admin.test", "Synthetic-admin-123!", "admin")
        self.app.auth.provision_staff("nurse.test", "Synthetic-nurse-123!", "nurse")
        self.admin = self.app.auth.login("admin.test", "Synthetic-admin-123!")
        self.nurse = self.app.auth.login("nurse.test", "Synthetic-nurse-123!")
        self.fields = dict(
            name="Taylor Example",
            date_of_birth="1994-03-12",
            email="taylor@example.com",
        )
        self.patient = self.app.patients.create(self.nurse, **self.fields)

    def client_login(self, username="admin.test", password="Synthetic-admin-123!"):
        client = self.web.test_client()
        client.get("/login")
        self.post(client, "/login", username=username, password=password)
        return client

    def post(self, client, path, **data):
        with client.session_transaction() as session:
            csrf = session["csrf"]
        return client.post(path, data=dict(csrf=csrf, **data))

    def make_note(self):
        return self.app.visits.add(
            self.nurse, self.patient.patient_id, "2026-01-01", "Synthetic cough"
        )


class PatientFixTests(V2Fixture):
    def test_collision_retries_without_duplicate_rows_or_audit(self):
        original = SimpleNamespace(hex=self.patient.patient_id.removeprefix("PAT-"))
        fresh = uuid4()
        with patch(
            "prs.patient.service.uuid4", side_effect=[original, fresh]
        ) as generate:
            created = self.app.patients.create(self.nurse, **self.fields)
        self.assertEqual(created.patient_id, "PAT-" + fresh.hex)
        self.assertEqual(generate.call_count, 2)
        with self.app.database.connect() as db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM patients").fetchone()[0], 2
            )
            self.assertEqual(
                db.execute(
                    "SELECT count(*) FROM audit_log WHERE action='patient_created'"
                ).fetchone()[0],
                2,
            )
        self.assertEqual(
            self.app.patients.get(self.nurse, self.patient.patient_id), self.patient
        )

    def test_persistent_collision_is_bounded(self):
        original = SimpleNamespace(hex=self.patient.patient_id.removeprefix("PAT-"))
        with patch("prs.patient.service.uuid4", return_value=original) as generate:
            with self.assertRaisesRegex(ConflictError, "allocate a unique"):
                self.app.patients.create(self.nurse, **self.fields)
        self.assertEqual(generate.call_count, self.app.patients.MAX_ID_ATTEMPTS)

    def test_unrelated_integrity_error_is_not_retried(self):
        # Fail the audit write: both patient insert and audit must roll back.
        with patch(
            "prs.persistence.repositories.audit",
            side_effect=sqlite3.IntegrityError("synthetic audit failure"),
        ):
            with patch("prs.patient.service.uuid4", return_value=uuid4()) as generate:
                with self.assertRaises(sqlite3.IntegrityError):
                    self.app.patients.create(self.nurse, **self.fields)
        self.assertEqual(generate.call_count, 1)
        with self.app.database.connect() as db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM patients").fetchone()[0], 1
            )

    def test_dob_missing_blank_invalid_and_future_rejected(self):
        for dob in [None, "", " ", "2026-02-30", "2999-01-01"]:
            with self.subTest(dob=dob), self.assertRaises(ValidationError):
                self.app.patients.create(
                    self.nurse, **dict(self.fields, date_of_birth=dob)
                )
        fields = self.fields.copy()
        fields.pop("date_of_birth")
        with self.assertRaises(ValidationError):
            self.app.patients.create(self.nurse, **fields)

    def test_email_only_phone_only_and_both_accepted(self):
        for contact in [
            dict(email="fake@example.com"),
            dict(email="", phone="202-555-0112"),
            dict(email="fake@example.com", phone="202-555-0112"),
        ]:
            patient = self.app.patients.create(
                self.nurse, **dict(self.fields, **contact)
            )
            self.assertTrue(patient.email or patient.phone)

    def test_neither_contact_or_invalid_supplied_contact_rejected(self):
        for contact in [
            dict(email="", phone=""),
            dict(email=" ", phone=" "),
            dict(email="bad", phone="202-555-0112"),
            dict(email="fake@example.com", phone="bad"),
        ]:
            with self.subTest(contact=contact), self.assertRaises(ValidationError):
                self.app.patients.create(self.nurse, **dict(self.fields, **contact))

    def test_update_cannot_clear_dob_or_last_contact(self):
        for changes in [dict(date_of_birth=""), dict(email="", phone="")]:
            with self.assertRaises(ValidationError):
                self.app.patients.update(
                    self.nurse, self.patient.patient_id, 0, **changes
                )
        self.assertEqual(
            self.app.patients.get(self.nurse, self.patient.patient_id), self.patient
        )
        changed = self.app.patients.update(
            self.nurse, self.patient.patient_id, 0, email="", phone="202-555-0101"
        )
        self.assertEqual(changed.patient_id, self.patient.patient_id)
        self.assertEqual(changed.email, "")
        self.assertTrue(changed.phone)

    def test_domain_and_database_enforce_required_fields(self):
        self.assertFalse(hasattr(self.patient, "__dict__"))
        with self.assertRaises(ValidationError):
            replace(self.patient, date_of_birth=None)
        with self.assertRaises(ValidationError):
            replace(self.patient, email="", phone="")
        for sql in [
            "UPDATE patients SET date_of_birth=NULL",
            "UPDATE patients SET date_of_birth=''",
            "UPDATE patients SET email='', phone=''",
            "UPDATE patients SET email=' ', phone=' '",
        ]:
            with (
                self.assertRaises(sqlite3.IntegrityError),
                self.app.database.connect() as db,
            ):
                db.execute(sql)

    def test_version_1_database_refused_without_schema_changes(self):
        path = Path(self.temp.name) / "legacy.sqlite3"
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE patients(patient_id TEXT PRIMARY KEY)")
            db.execute("INSERT INTO patients VALUES('legacy-patient')")
        before = path.read_bytes()
        with self.assertRaisesRegex(ValidationError, "Version 2 database"):
            create_app(str(path), self.provider, testing=True)
        self.assertEqual(path.read_bytes(), before)

    def test_patient_detail_fetches_patient_once(self):
        note = self.make_note()
        client = self.client_login("nurse.test", "Synthetic-nurse-123!")
        statements = []
        real_connect = self.app.database.connect

        @contextmanager
        def traced_connect():
            with real_connect() as db:
                db.set_trace_callback(statements.append)
                yield db

        with patch.object(self.app.database, "connect", traced_connect):
            response = client.get("/patients/" + self.patient.patient_id)
        self.assertEqual(response.status_code, 200)
        patient_reads = [
            s for s in statements if s.startswith("SELECT * FROM patients WHERE")
        ]
        all_reads = [s for s in statements if s.startswith("SELECT ")]
        self.assertEqual(len(patient_reads), 1)
        self.assertEqual(len(all_reads), 5)
        self.assertIn(note.text, response.get_data(as_text=True))


class AdminWorkflowTests(V2Fixture):
    def test_admin_creates_both_roles_through_web_and_accounts_survive_restart(self):
        client = self.client_login()
        self.assertIn("/admin/staff/new", client.get("/").headers["Location"])
        self.assertEqual(client.get("/admin/staff/new").status_code, 200)
        for role in ["doctor", "nurse"]:
            username = role + ".created"
            response = self.post(
                client,
                "/admin/staff/new",
                username=username,
                role=role,
                password="Synthetic-created-123!",
                confirm_password="Synthetic-created-123!",
            )
            self.assertEqual(response.status_code, 302)
            new_token = self.app.auth.login(username, "Synthetic-created-123!")
            self.assertEqual(self.app.auth.require(new_token).role, role)
            self.app.patients.get(new_token, self.patient.patient_id)
        restarted = create_app(
            self.database_path, self.provider, testing=True
        ).extensions["prs"]
        token = restarted.auth.login("doctor.created", "Synthetic-created-123!")
        self.assertEqual(restarted.auth.require(token).role, "doctor")
        with restarted.database.connect() as db:
            events = db.execute(
                "SELECT * FROM audit_log WHERE action='staff_created'"
            ).fetchall()
        self.assertEqual(len(events), 2)
        self.assertNotIn("Synthetic-created", str([dict(event) for event in events]))

    def test_nonadmin_denied_on_route_and_service(self):
        for role in ["doctor", "nurse", "viewer"]:
            username = role + ".restricted"
            self.app.auth.provision_staff(username, "Synthetic-limited-123!", role)
            token = self.app.auth.login(username, "Synthetic-limited-123!")
            with self.assertRaises(AuthorizationError):
                self.app.auth.create_staff(
                    token, "unauthorized", "Synthetic-denied-123!", "nurse"
                )
            client = self.client_login(username, "Synthetic-limited-123!")
            self.assertEqual(client.get("/admin/staff/new").status_code, 403)
            response = self.post(
                client,
                "/admin/staff/new",
                username="unauthorized",
                role="doctor",
                password="Synthetic-denied-123!",
                confirm_password="Synthetic-denied-123!",
            )
            self.assertEqual(response.status_code, 403)
        self.assertIsNone(self.app.auth.repository.by_username("unauthorized"))

    def test_admin_cannot_read_or_edit_patient_records(self):
        client = self.client_login()
        self.assertEqual(
            client.get("/patients/" + self.patient.patient_id).status_code, 403
        )
        with self.assertRaises(AuthorizationError):
            self.app.patients.create(self.admin, **self.fields)
        with self.assertRaises(AuthorizationError):
            self.app.records.get(self.admin, self.patient.patient_id)

    def test_invalid_role_duplicate_username_and_passwords(self):
        client = self.client_login()
        cases = [
            dict(
                username="new.person",
                role="admin",
                password="Synthetic-created-123!",
                confirm_password="Synthetic-created-123!",
            ),
            dict(
                username="new.person",
                role="doctor",
                password="short",
                confirm_password="short",
            ),
            dict(
                username="new.person",
                role="doctor",
                password="Synthetic-created-123!",
                confirm_password="different",
            ),
            dict(
                username="new.person",
                role="viewer",
                password="Synthetic-created-123!",
                confirm_password="Synthetic-created-123!",
            ),
        ]
        for data in cases:
            self.assertEqual(
                self.post(client, "/admin/staff/new", **data).status_code, 400
            )
        duplicate = self.post(
            client,
            "/admin/staff/new",
            username="NURSE.TEST",
            role="doctor",
            password="Synthetic-created-123!",
            confirm_password="Synthetic-created-123!",
        )
        self.assertEqual(duplicate.status_code, 409)
        self.assertNotIn("Synthetic-created-123!", duplicate.get_data(as_text=True))
        self.assertIsNone(self.app.auth.repository.by_username("new.person"))

    def test_admin_csrf_and_unauthenticated_requests_rejected(self):
        client = self.client_login()
        self.assertEqual(
            client.post("/admin/staff/new", data=dict(username="forged")).status_code,
            403,
        )
        guest = self.web.test_client()
        self.assertEqual(guest.get("/admin/staff/new").status_code, 302)

    def test_new_patient_ui_validation_preserves_input(self):
        client = self.client_login("nurse.test", "Synthetic-nurse-123!")
        response = self.post(
            client,
            "/patients/new",
            name="Synthetic Preserved",
            email="fake@example.com",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Synthetic Preserved", response.get_data(as_text=True))
        response = self.post(
            client,
            "/patients/new",
            name="Synthetic Preserved",
            date_of_birth="1994-03-12",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("at least one contact", response.get_data(as_text=True))


class SuggestionFixTests(V2Fixture):
    def test_acceptance_database_failure_preserves_suggestion_for_retry(self):
        note = self.make_note()
        result = self.app.visits.suggest(self.nurse, note.note_id)
        with patch.object(
            self.app.visits.repository,
            "categorize",
            side_effect=sqlite3.OperationalError("locked"),
        ):
            with self.assertRaises(sqlite3.OperationalError):
                self.app.visits.review(
                    self.nurse, note.note_id, result.suggestion.suggestion_id, "accept"
                )
        self.assertEqual(self.app.categorizer.suggestions.pending_count, 1)
        self.assertIsNone(self.app.visits.get(self.nurse, note.note_id).category)
        accepted = self.app.visits.review(
            self.nurse, note.note_id, result.suggestion.suggestion_id, "accept"
        )
        self.assertEqual(accepted.category, "Respiratory")
        self.assertEqual(self.app.categorizer.suggestions.pending_count, 0)

    def test_rejection_database_failure_preserves_suggestion_for_retry(self):
        note = self.make_note()
        result = self.app.visits.suggest(self.nurse, note.note_id)
        with patch.object(
            self.app.visits.repository,
            "reject",
            side_effect=sqlite3.OperationalError("locked"),
        ):
            with self.assertRaises(sqlite3.OperationalError):
                self.app.visits.review(
                    self.nurse, note.note_id, result.suggestion.suggestion_id, "reject"
                )
        self.app.visits.review(
            self.nurse, note.note_id, result.suggestion.suggestion_id, "reject"
        )
        self.assertEqual(self.app.categorizer.suggestions.pending_count, 0)
        self.assertIsNone(self.app.visits.get(self.nurse, note.note_id).category)

    def test_reserved_suggestion_blocks_other_review_and_expiry_applies(self):
        store = SuggestionStore()
        suggestion = store.add("note", "user", Category.RESPIRATORY, 0.9, 0)
        with store.reserve(suggestion.suggestion_id, "note", "user"):
            with self.assertRaisesRegex(ConflictError, "already being reviewed"):
                with store.reserve(suggestion.suggestion_id, "note", "user"):
                    self.fail("Concurrent review should not be allowed")
        self.assertEqual(store.pending_count, 0)
        expired = SuggestionStore(lifetime=-1)
        suggestion = expired.add("note", "user", Category.RESPIRATORY, 0.9, 0)
        with self.assertRaises(ConflictError):
            with expired.reserve(suggestion.suggestion_id, "note", "user"):
                self.fail("Expired suggestion should not be reviewable")

    def test_provider_errors_are_logged_without_note_text(self):
        note = self.make_note()
        with patch.object(
            self.provider, "suggest", side_effect=ProviderUnavailableError(note.text)
        ):
            with self.assertLogs(
                "prs.ai_integration.inference", level="WARNING"
            ) as logs:
                result = self.app.visits.suggest(self.nurse, note.note_id)
        self.assertEqual(result.status, "unavailable")
        self.assertIn("ProviderUnavailableError", str(logs.output))
        self.assertNotIn(note.text, str(logs.output))

from dataclasses import FrozenInstanceError
from datetime import date
import json
from pathlib import Path
import re
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from prs.ai_integration.providers import CategorizationProvider, DisabledProvider, OllamaProvider, Prediction
from prs.ai_integration.service import CategorizationService
from prs.application import PRSApplication
from prs.errors import AuthenticationError, AuthorizationError, ConflictError, NotFoundError, ValidationError
from prs.models import Category
from prs.ui.web import create_app


class TestProvider(CategorizationProvider):
    """TEST SUBSTITUTE ONLY. Returns injected results; this is not an AI model."""
    def __init__(self, prediction=None, delay=0, error=False):
        self.prediction = prediction or Prediction(Category.RESPIRATORY, 0.9, False)
        self.delay, self.error, self.inputs = delay, error, []

    def suggest(self, note_text):
        self.inputs.append(note_text)
        time.sleep(self.delay)
        if self.error:
            raise ConnectionError("Synthetic outage")
        return self.prediction


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name) / "test.sqlite3")
        self.provider = TestProvider()
        self.app = PRSApplication(self.path, self.provider, ai_timeout=0.05)
        self.app.auth.provision_staff("nurse.test", "Synthetic-pass-123!", "nurse")
        self.app.auth.provision_staff("viewer.test", "Synthetic-pass-456!", "viewer")
        self.token = self.app.auth.login("nurse.test", "Synthetic-pass-123!")
        self.viewer = self.app.auth.login("viewer.test", "Synthetic-pass-456!")
        self.patient = self.app.patients.create(self.token, name="Alex Example", email="alex@example.com")

    def note(self, text="Synthetic note: coughing.", day="2026-01-01"):
        return self.app.visits.add(self.token, self.patient.patient_id, day, text)

    def test_ids_unique_and_immutable(self):
        other = self.app.patients.create(self.token, name="Alex Example")
        self.assertNotEqual(other.patient_id, self.patient.patient_id)
        with self.assertRaises(FrozenInstanceError):
            self.patient.patient_id = "changed"
        with self.assertRaises(ValidationError):
            self.app.patients.update(self.token, self.patient.patient_id, 0, patient_id_new="changed")
        with self.assertRaises(sqlite3.IntegrityError), self.app.database.connect() as db:
            db.execute("UPDATE patients SET patient_id='changed' WHERE patient_id=?", (self.patient.patient_id,))

    def test_patient_update_and_audit(self):
        updated = self.app.patients.update(self.token, self.patient.patient_id, 0, phone="202-555-0100")
        self.assertEqual(updated.patient_id, self.patient.patient_id)
        self.assertEqual(updated.phone, "202-555-0100")
        changes = self.app.patients.changes(self.token, self.patient.patient_id)
        self.assertIn("202-555-0100", changes[0]["details"])

    def test_concurrent_patient_update_rejected(self):
        self.app.patients.update(self.token, self.patient.patient_id, 0, name="Changed Example")
        with self.assertRaises(ConflictError):
            self.app.patients.update(self.token, self.patient.patient_id, 0, name="Stale Example")
        self.assertEqual(self.app.patients.get(self.token, self.patient.patient_id).name, "Changed Example")

    def test_validation_and_optional_contact(self):
        for fields in ({"name": " "}, {"name": "Example", "email": "bad"},
                       {"name": "Example", "date_of_birth": "2026-02-30"}):
            with self.assertRaises(ValidationError):
                self.app.patients.create(self.token, **fields)
        self.assertEqual(self.app.patients.create(self.token, name="Name Only").email, "")

    def test_missing_patient_no_mutation(self):
        with self.assertRaisesRegex(NotFoundError, "Patient not found"):
            self.app.patients.get(self.token, "missing")
        with self.assertRaises(NotFoundError):
            self.app.visits.add(self.token, "missing", "2026-01-01", "Synthetic note")
        with self.app.database.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM visit_notes").fetchone()[0], 0)

    def test_note_validation_and_patient_link(self):
        for day, text in (("bad", "note"), ("2026-02-30", "note"), ("2026-01-01", " "), ("2999-01-01", "note")):
            with self.assertRaises(ValidationError):
                self.note(text, day)
        note = self.note()
        self.assertEqual(note.patient_id, self.patient.patient_id)
        for sql in ("UPDATE visit_notes SET text='changed'", "UPDATE visit_notes SET patient_id='missing'",
                    "UPDATE visit_notes SET visit_date='2020-01-01'", "DELETE FROM visit_notes"):
            with self.assertRaises(sqlite3.IntegrityError), self.app.database.connect() as db:
                db.execute(sql)

    def test_foreign_key_rejects_orphan(self):
        note = self.note()
        with self.assertRaises(sqlite3.IntegrityError), self.app.database.connect() as db:
            db.execute("""INSERT INTO visit_notes(note_id,patient_id,visit_date,text,author_id,created_at)
                VALUES('orphan','missing','2026-01-01','Synthetic',?,'now')""", (note.author_id,))

    def test_history_sorted_and_isolated(self):
        first = self.note(day="2026-01-01")
        second = self.note(day="2026-02-01")
        other = self.app.patients.create(self.token, name="Other Example")
        self.app.visits.add(self.token, other.patient_id, "2026-03-01", "Other synthetic note")
        history = self.app.visits.history(self.token, self.patient.patient_id)
        self.assertEqual([n.note_id for n in history], [second.note_id, first.note_id])

    def test_authentication_and_logout(self):
        with self.assertRaises(AuthenticationError):
            self.app.auth.login("nurse.test", "wrong")
        self.app.auth.logout(self.token)
        with self.assertRaises(AuthenticationError):
            self.app.patients.get(self.token, self.patient.patient_id)

    def test_forged_token_expiry_and_deactivated_account(self):
        with self.assertRaises(AuthenticationError):
            self.app.patients.get("forged", self.patient.patient_id)
        user_id = self.app.auth.require(self.token).user_id
        with self.app.auth._lock:
            self.app.auth._sessions[self.token] = (user_id, 0)
        with self.assertRaises(AuthenticationError):
            self.app.patients.get(self.token, self.patient.patient_id)
        fresh = self.app.auth.login("nurse.test", "Synthetic-pass-123!")
        with self.app.database.connect() as db:
            db.execute("UPDATE staff SET active=0 WHERE user_id=?", (user_id,))
        with self.assertRaises(AuthenticationError):
            self.app.patients.get(fresh, self.patient.patient_id)

    def test_viewer_can_read_but_cannot_write(self):
        note = self.note()
        self.app.patients.get(self.viewer, self.patient.patient_id)
        self.assertEqual(len(self.app.visits.history(self.viewer, self.patient.patient_id)), 1)
        operations = [lambda: self.app.patients.create(self.viewer, name="Denied"),
                      lambda: self.app.patients.update(self.viewer, self.patient.patient_id, 0, name="Denied"),
                      lambda: self.app.visits.add(self.viewer, self.patient.patient_id, "2026-01-01", "Denied"),
                      lambda: self.app.visits.suggest(self.viewer, note.note_id),
                      lambda: self.app.visits.review(self.viewer, note.note_id, "fake", "accept"),
                      lambda: self.app.visits.manual_category(self.viewer, note.note_id, "Respiratory", 0)]
        for operation in operations:
            with self.assertRaises(AuthorizationError):
                operation()

    def test_password_hash_and_login_throttle(self):
        row = self.app.auth.repository.by_username("nurse.test")
        self.assertNotIn("Synthetic-pass", row["password_hash"])
        for _ in range(5):
            with self.assertRaises(AuthenticationError):
                self.app.auth.login("nurse.test", "bad")
        with self.assertRaisesRegex(AuthenticationError, "Too many"):
            self.app.auth.login("nurse.test", "Synthetic-pass-123!")

    def test_save_does_not_call_ai(self):
        self.provider.error = True
        note = self.note()
        self.assertEqual(self.provider.inputs, [])
        self.assertIsNone(note.category)

    def test_suggestion_not_persisted_until_acceptance(self):
        note = self.note()
        result = self.app.visits.suggest(self.token, note.note_id)
        self.assertEqual(result.status, "suggested")
        self.assertEqual(self.provider.inputs, [note.text])
        self.assertIsNone(self.app.visits.get(self.token, note.note_id).category)
        with self.app.database.connect() as db:
            self.assertNotIn("Respiratory", " ".join(row[0] for row in db.execute("SELECT details FROM audit_log")))
        updated = self.app.visits.review(self.token, note.note_id, result.suggestion.suggestion_id, "accept")
        self.assertEqual(updated.category, "Respiratory")
        self.assertEqual(updated.category_source, "ai_accepted")
        with self.assertRaises(ConflictError):
            self.app.visits.review(self.token, note.note_id, result.suggestion.suggestion_id, "accept")

    def test_rejection_and_manual_categories(self):
        note = self.note()
        result = self.app.visits.suggest(self.token, note.note_id)
        self.app.visits.review(self.token, note.note_id, result.suggestion.suggestion_id, "reject")
        self.assertIsNone(self.app.visits.get(self.token, note.note_id).category)
        for version, category in enumerate(Category):
            updated = self.app.visits.manual_category(self.token, note.note_id, category.value, version)
            self.assertEqual(updated.category, category.value)
        with self.assertRaises(ValidationError):
            self.app.visits.manual_category(self.token, note.note_id, "Invalid category", 4)

    def test_wrong_staff_wrong_note_and_stale_suggestion(self):
        note = self.note()
        other = self.note("Another synthetic visit")
        result = self.app.visits.suggest(self.token, note.note_id)
        self.app.auth.provision_staff("doctor.test", "Synthetic-pass-789!", "doctor")
        doctor = self.app.auth.login("doctor.test", "Synthetic-pass-789!")
        with self.assertRaises(ConflictError):
            self.app.visits.review(doctor, note.note_id, result.suggestion.suggestion_id, "accept")
        with self.assertRaises(ConflictError):
            self.app.visits.review(self.token, other.note_id, result.suggestion.suggestion_id, "accept")
        self.app.visits.manual_category(self.token, note.note_id, "Digestive", 0)
        with self.assertRaises(ConflictError):
            self.app.visits.review(self.token, note.note_id, result.suggestion.suggestion_id, "accept")
        self.assertEqual(self.app.visits.get(self.token, note.note_id).category, "Digestive")

    def test_uncertain_error_timeout_and_late_response(self):
        note = self.note()
        self.provider.prediction = Prediction(Category.RESPIRATORY, 0.4, False)
        self.assertEqual(self.app.visits.suggest(self.token, note.note_id).status, "uncertain")
        self.provider.prediction = Prediction(None, 0.95, True)
        self.assertEqual(self.app.visits.suggest(self.token, note.note_id).status, "uncertain")
        self.provider.error = True
        self.assertEqual(self.app.visits.suggest(self.token, note.note_id).status, "unavailable")
        self.provider.error = False
        self.provider.delay = 0.15
        self.provider.prediction = Prediction(Category.RESPIRATORY, 0.9, False)
        started = time.monotonic()
        self.assertEqual(self.app.visits.suggest(self.token, note.note_id).status, "timeout")
        self.assertLess(time.monotonic() - started, 0.12)
        time.sleep(0.18)
        self.assertEqual(self.app.categorizer._pending, {})
        self.assertIsNone(self.app.visits.get(self.token, note.note_id).category)

    def test_restart_persistence_and_pending_suggestion_expiry(self):
        note = self.note()
        result = self.app.visits.suggest(self.token, note.note_id)
        self.app.visits.manual_category(self.token, note.note_id, "General/Other", 0)
        restarted = PRSApplication(self.path, DisabledProvider())
        token = restarted.auth.login("nurse.test", "Synthetic-pass-123!")
        self.assertEqual(restarted.patients.get(token, self.patient.patient_id), self.patient)
        self.assertEqual(restarted.visits.history(token, self.patient.patient_id)[0].category, "General/Other")
        with self.assertRaises(AuthenticationError):
            restarted.patients.get(self.token, self.patient.patient_id)
        with self.assertRaises(ConflictError):
            restarted.visits.review(token, note.note_id, result.suggestion.suggestion_id, "accept")

    def test_lookup_performance_and_sql_injection(self):
        started = time.perf_counter()
        self.app.patients.get(self.token, self.patient.patient_id)
        self.assertLess(time.perf_counter() - started, 2)
        with self.assertRaises(NotFoundError):
            self.app.patients.get(self.token, "' OR 1=1 --")


class AdapterTests(unittest.TestCase):
    def test_ollama_payload_and_strict_output(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, limit): return json.dumps({"done": True, "response": json.dumps(payload)}).encode()
        provider = OllamaProvider()
        payload = {"category": "Digestive", "confidence": 0.9, "uncertain": False}
        with patch("prs.ai_integration.providers.build_opener") as opener:
            opener.return_value.open.return_value = Response()
            self.assertEqual(provider.suggest("Synthetic note"), Prediction(Category.DIGESTIVE, 0.9, False))
            body = json.loads(opener.return_value.open.call_args.args[0].data)
            self.assertFalse(body["stream"])
            self.assertEqual(json.loads(body["prompt"]), {"synthetic_visit_note": "Synthetic note"})
            for payload in ({"category": "Invalid", "confidence": 0.9, "uncertain": False},
                            {"category": "Digestive", "confidence": "high", "uncertain": False},
                            {"category": "Digestive", "confidence": float("nan"), "uncertain": False}):
                with self.assertRaises(ValueError):
                    provider.suggest("Synthetic note")

    def test_remote_provider_not_permitted(self):
        with self.assertRaises(ValueError):
            OllamaProvider(base_url="https://example.com")

    def test_hard_wall_clock_deadline(self):
        provider = TestProvider(delay=5.2)
        service = CategorizationService(provider)
        started = time.monotonic()
        self.assertEqual(service.request("note", "synthetic", "user", 0).status, "timeout")
        self.assertLess(time.monotonic() - started, 5.0)

    def test_stuck_workers_are_bounded(self):
        provider = TestProvider(delay=0.2)
        service = CategorizationService(provider, timeout=0.005)
        for _ in range(4):
            self.assertEqual(service.request("note", "synthetic", "user", 0).status, "timeout")
        self.assertEqual(service.request("note", "synthetic", "user", 0).status, "unavailable")


class WebTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = create_app(str(Path(self.temp.name) / "web.sqlite3"), TestProvider(), testing=True)
        self.services = self.app.extensions["prs"]
        self.services.auth.provision_staff("nurse.web", "Synthetic-web-123!", "nurse")
        self.client = self.app.test_client()
        self.client.get("/login")

    def csrf(self):
        with self.client.session_transaction() as session:
            return session["csrf"]

    def post(self, path, **data):
        return self.client.post(path, data=dict(csrf=self.csrf(), **data))

    def login(self):
        return self.post("/login", username="nurse.web", password="Synthetic-web-123!")

    def test_csrf_and_auth_guards(self):
        self.assertEqual(self.client.get("/").status_code, 302)
        self.client.get("/login")
        self.assertEqual(self.client.post("/login", data={"username": "nurse.web"}).status_code, 403)
        self.login()
        self.assertEqual(self.client.post("/patients/new", data={"name": "Synthetic"}).status_code, 403)
        self.assertEqual(self.post("/patients/new", name="Synthetic", patient_id="injected").status_code, 400)

    def test_web_full_workflow_and_escaped_content(self):
        self.login()
        response = self.post("/patients/new", name="<script>test</script>", email="fake@example.com")
        self.assertEqual(response.status_code, 302)
        location = response.headers["Location"]
        html = self.client.get(location).get_data(as_text=True)
        self.assertIn("&lt;script&gt;test&lt;/script&gt;", html)
        self.assertNotIn("<script>test</script>", html)
        self.assertEqual(self.post(location + "/notes", visit_date="2026-01-01", text="Synthetic cough").status_code, 302)
        with self.services.database.connect() as db:
            note_id = db.execute("SELECT note_id FROM visit_notes").fetchone()[0]
        result = self.post(f"/notes/{note_id}/suggest").get_json()
        self.assertEqual(result["status"], "suggested")
        self.assertEqual(self.post(f"/notes/{note_id}/review", suggestion_id=result["suggestion_id"], decision="accept").status_code, 302)
        self.assertIn("Respiratory", self.client.get(location).get_data(as_text=True))
        self.post("/logout")
        self.assertEqual(self.client.get(location).status_code, 302)


if __name__ == "__main__":
    unittest.main()

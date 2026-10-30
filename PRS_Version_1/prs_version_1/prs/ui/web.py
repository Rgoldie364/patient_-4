from datetime import date
from functools import wraps
import os
from pathlib import Path
import secrets
import sqlite3

from flask import Flask, flash, g, jsonify, redirect, render_template, request, session, url_for

from prs.ai_integration.providers import DisabledProvider, OllamaProvider
from prs.application import PRSApplication
from prs.authentication.service import PERMISSIONS
from prs.errors import PRSError, AuthenticationError, AuthorizationError, ValidationError
from prs.models import Category


def create_app(database_path=None, provider=None, testing=False, ai_timeout=4.75):
    app = Flask(__name__)
    app.config.update(SECRET_KEY=secrets.token_hex(32), TESTING=testing,
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Strict",
                      MAX_CONTENT_LENGTH=32768)
    project = Path(__file__).resolve().parents[2]
    path = database_path or os.environ.get("PRS_DB", str(project / "data" / "prs_v1.sqlite3"))
    if provider is None:
        provider = (DisabledProvider() if os.environ.get("PRS_AI", "ollama") == "disabled" else
                    OllamaProvider(os.environ.get("PRS_OLLAMA_MODEL", "qwen2.5:3b"),
                                   os.environ.get("PRS_OLLAMA_URL", "http://127.0.0.1:11434")))
    services = PRSApplication(path, provider, ai_timeout)
    app.extensions["prs"] = services

    def token():
        return session.get("token")

    def protected(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            g.staff = services.auth.require(token())
            return view(*args, **kwargs)
        return wrapped

    @app.before_request
    def csrf_protection():
        if "csrf" not in session:
            session["csrf"] = secrets.token_urlsafe(32)
        if request.method == "POST":
            supplied = request.form.get("csrf") or request.headers.get("X-CSRF-Token", "")
            if not secrets.compare_digest(session["csrf"], supplied):
                raise AuthorizationError("Form expired or could not be verified. Reload the page and try again.")

    @app.after_request
    def headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        return response

    @app.context_processor
    def context():
        staff = getattr(g, "staff", None)
        return dict(staff=staff, can_write=bool(staff and "patient_write" in PERMISSIONS[staff.role]),
                    categories=[c.value for c in Category], today=date.today().isoformat())

    @app.errorhandler(PRSError)
    def error(exc):
        if request.path.endswith("/suggest"):
            return jsonify(error=str(exc)), exc.status_code
        if isinstance(exc, AuthenticationError) and request.endpoint != "login":
            session.clear()
            return redirect(url_for("login"))
        return render_template("error.html", message=str(exc)), exc.status_code

    @app.errorhandler(sqlite3.OperationalError)
    def database_error(exc):
        app.logger.error("Database operation failed (%s)", type(exc).__name__)
        message = "Storage is temporarily unavailable. The operation was not confirmed. Reload to check before retrying."
        if request.path.endswith("/suggest"):
            return jsonify(error=message), 503
        return render_template("error.html", message=message), 503

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            new_token = services.auth.login(request.form.get("username", ""), request.form.get("password", ""))
            services.auth.logout(token())
            session.clear()
            session.update(token=new_token, csrf=secrets.token_urlsafe(32))
            return redirect(url_for("home"))
        return render_template("login.html")

    @app.post("/logout")
    def logout():
        services.auth.logout(token())
        session.clear()
        return redirect(url_for("login"))

    @app.get("/")
    @protected
    def home():
        return render_template("home.html")

    @app.get("/patients/search")
    @protected
    def search():
        patient = services.patients.get(token(), request.args.get("patient_id", "").strip())
        return redirect(url_for("patient_detail", patient_id=patient.patient_id))

    def submitted_patient_fields():
        unexpected = set(request.form) - services.patients.EDITABLE - {"csrf", "version"}
        if unexpected:
            raise ValidationError("The request contains a field that cannot be edited.")
        return {key: request.form.get(key, "") for key in services.patients.EDITABLE}

    @app.route("/patients/new", methods=["GET", "POST"])
    @protected
    def patient_new():
        services.auth.require(token(), "patient_write")
        if request.method == "POST":
            patient = services.patients.create(token(), **submitted_patient_fields())
            flash("Patient created. The permanent Patient ID is shown below.")
            return redirect(url_for("patient_detail", patient_id=patient.patient_id))
        return render_template("patient_form.html", patient=None)

    @app.route("/patients/<patient_id>/edit", methods=["GET", "POST"])
    @protected
    def patient_edit(patient_id):
        services.auth.require(token(), "patient_write")
        if request.method == "POST":
            services.patients.update(token(), patient_id, request.form.get("version"), **submitted_patient_fields())
            flash("Patient information updated.")
            return redirect(url_for("patient_detail", patient_id=patient_id))
        return render_template("patient_form.html", patient=services.patients.get(token(), patient_id))

    @app.get("/patients/<patient_id>")
    @protected
    def patient_detail(patient_id):
        return render_template("patient.html", patient=services.patients.get(token(), patient_id),
                               notes=services.visits.history(token(), patient_id),
                               changes=services.patients.changes(token(), patient_id))

    @app.post("/patients/<patient_id>/notes")
    @protected
    def add_note(patient_id):
        services.visits.add(token(), patient_id, request.form.get("visit_date", ""), request.form.get("text", ""))
        flash("Visit note saved. You may now request an AI suggestion or choose a category manually.")
        return redirect(url_for("patient_detail", patient_id=patient_id, _anchor="history"))

    @app.post("/notes/<note_id>/suggest")
    @protected
    def suggest(note_id):
        result = services.visits.suggest(token(), note_id)
        payload = {"status": result.status}
        if result.suggestion:
            payload.update(suggestion_id=result.suggestion.suggestion_id, category=result.suggestion.category.value)
        return jsonify(payload)

    @app.post("/notes/<note_id>/review")
    @protected
    def review(note_id):
        note = services.visits.review(token(), note_id, request.form.get("suggestion_id"), request.form.get("decision"))
        flash("Suggested category accepted." if request.form["decision"] == "accept" else "Suggestion rejected. The saved category was not changed.")
        return redirect(url_for("patient_detail", patient_id=note.patient_id, _anchor="history"))

    @app.post("/notes/<note_id>/category")
    @protected
    def manual_category(note_id):
        note = services.visits.manual_category(token(), note_id, request.form.get("category"), request.form.get("category_version"))
        flash("Manual category saved.")
        return redirect(url_for("patient_detail", patient_id=note.patient_id, _anchor="history"))

    return app

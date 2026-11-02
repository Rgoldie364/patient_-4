"""Shared request protections, response headers, and error rendering."""

import secrets
import sqlite3
from datetime import date

from flask import g, jsonify, redirect, render_template, request, session, url_for

from prs.authentication.service import PERMISSIONS
from prs.errors import AuthenticationError, AuthorizationError, PRSError
from prs.models import Category


def register_handlers(app):
    """Attach shared handlers without mixing them with feature routes."""

    @app.before_request
    def csrf_protection():
        if "csrf" not in session:
            session["csrf"] = secrets.token_urlsafe(32)
        if request.method == "POST":
            supplied = request.form.get("csrf") or request.headers.get(
                "X-CSRF-Token", ""
            )
            if not secrets.compare_digest(session["csrf"], supplied):
                raise AuthorizationError(
                    "Form expired or could not be verified. Reload the page and try again."
                )

    @app.after_request
    def headers(response):
        response.headers.update(
            {
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "Referrer-Policy": "no-referrer",
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
            }
        )
        return response

    @app.context_processor
    def context():
        staff = getattr(g, "staff", None)
        permissions = PERMISSIONS.get(staff.role, ()) if staff else ()
        return dict(
            staff=staff,
            can_write="patient_write" in permissions,
            can_manage_staff="manage_staff" in permissions,
            categories=[category.value for category in Category],
            today=date.today().isoformat(),
        )

    @app.errorhandler(PRSError)
    def error(exc):
        if request.endpoint == "visits.suggest":
            return jsonify(error=str(exc)), exc.status_code
        if isinstance(exc, AuthenticationError) and request.endpoint != "auth.login":
            session.clear()
            return redirect(url_for("auth.login"))
        return render_template("error.html", message=str(exc)), exc.status_code

    @app.errorhandler(sqlite3.OperationalError)
    @app.errorhandler(sqlite3.IntegrityError)
    def database_error(exc):
        app.logger.error("Database operation failed (%s)", type(exc).__name__)
        message = "Storage could not complete the operation. Reload to check the saved record before retrying."
        if request.endpoint == "visits.suggest":
            return jsonify(error=message), 503
        return render_template("error.html", message=message), 503

"""Small Flask application factory; feature routes live in separate blueprints."""

import os
import secrets
from pathlib import Path

from flask import Flask

from prs.ai_integration.providers import DisabledProvider, OllamaProvider
from prs.application import PRSApplication
from prs.ui import admin_routes, auth_routes, patient_routes, visit_routes
from prs.ui.handlers import register_handlers


def create_app(database_path=None, provider=None, testing=False, ai_timeout=4.75):
    """Configure and assemble the local Version 2 application."""
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=secrets.token_hex(32),
        TESTING=testing,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        MAX_CONTENT_LENGTH=32768,
    )
    project = Path(__file__).resolve().parents[2]
    path = database_path or os.environ.get(
        "PRS_DB", str(project / "data" / "prs_v2.sqlite3")
    )
    if provider is None:
        provider = (
            DisabledProvider()
            if os.environ.get("PRS_AI", "ollama") == "disabled"
            else OllamaProvider(
                os.environ.get("PRS_OLLAMA_MODEL", "qwen2.5:3b"),
                os.environ.get("PRS_OLLAMA_URL", "http://127.0.0.1:11434"),
            )
        )
    app.extensions["prs"] = PRSApplication(path, provider, ai_timeout)
    register_handlers(app)
    for blueprint in (
        auth_routes.bp,
        patient_routes.bp,
        visit_routes.bp,
        admin_routes.bp,
    ):
        app.register_blueprint(blueprint)
    return app

"""Small shared UI adapters; authorization remains in business services."""

from functools import wraps

from flask import current_app, g, session


def services():
    return current_app.extensions["prs"]


def token() -> str | None:
    return session.get("token")


def protected(view):
    """Authenticate a route without granting clinical permissions to admins."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        g.staff = services().auth.require(token(), permission=None)
        return view(*args, **kwargs)

    return wrapped

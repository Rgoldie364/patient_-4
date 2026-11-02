"""Staff sign-in and sign-out routes."""

import secrets

from flask import Blueprint, redirect, render_template, request, session, url_for

from prs.ui.common import services, token

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        new_token = services().auth.login(
            request.form.get("username", ""), request.form.get("password", "")
        )
        services().auth.logout(token())
        session.clear()
        session.update(token=new_token, csrf=secrets.token_urlsafe(32))
        return redirect(url_for("patients.home"))
    return render_template("login.html")


@bp.post("/logout")
def logout():
    services().auth.logout(token())
    session.clear()
    return redirect(url_for("auth.login"))

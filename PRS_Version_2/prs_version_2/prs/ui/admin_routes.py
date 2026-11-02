"""Admin-only creation of doctor and nurse accounts."""

from flask import Blueprint, flash, redirect, render_template, request, url_for

from prs.errors import ConflictError, ValidationError
from prs.ui.common import protected, services, token

bp = Blueprint("admin", __name__)


@bp.route("/admin/staff/new", methods=["GET", "POST"])
@protected
def staff_new():
    services().auth.require(token(), "manage_staff")
    if request.method == "POST":
        username = request.form.get("username", "")
        role = request.form.get("role", "")
        try:
            if request.form.get("password", "") != request.form.get(
                "confirm_password", ""
            ):
                raise ValidationError("Passwords do not match.")
            user = services().auth.create_staff(
                token(), username, request.form.get("password", ""), role
            )
        except (ValidationError, ConflictError) as exc:
            return render_template(
                "staff_form.html", error=str(exc), username=username, selected_role=role
            ), exc.status_code
        flash(
            f"Created {user.role} account: {user.username}. The new staff member can now sign in."
        )
        return redirect(url_for("admin.staff_new"))
    return render_template("staff_form.html", username="", selected_role="doctor")

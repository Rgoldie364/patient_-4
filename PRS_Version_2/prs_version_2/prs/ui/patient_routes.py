"""Patient lookup, validated forms, and the combined patient record screen."""

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from prs.errors import ValidationError
from prs.ui.common import protected, services, token

bp = Blueprint("patients", __name__)


@bp.get("/")
@protected
def home():
    if g.staff.role == "admin":
        return redirect(url_for("admin.staff_new"))
    services().auth.require(token(), "read")
    return render_template("home.html")


@bp.get("/patients/search")
@protected
def search():
    patient = services().patients.get(
        token(), request.args.get("patient_id", "").strip()
    )
    return redirect(url_for("patients.patient_detail", patient_id=patient.patient_id))


def submitted_fields() -> dict:
    editable = services().patients.EDITABLE
    unexpected = set(request.form) - editable - {"csrf", "version"}
    if unexpected:
        raise ValidationError("The request contains a field that cannot be edited.")
    return {key: request.form.get(key, "") for key in editable}


@bp.route("/patients/new", methods=["GET", "POST"])
@protected
def patient_new():
    services().auth.require(token(), "patient_write")
    if request.method == "POST":
        try:
            patient = services().patients.create(token(), **submitted_fields())
        except ValidationError as exc:
            return render_template(
                "patient_form.html", patient=None, values=request.form, error=str(exc)
            ), 400
        flash("Patient created. The permanent Patient ID is shown below.")
        return redirect(
            url_for("patients.patient_detail", patient_id=patient.patient_id)
        )
    return render_template("patient_form.html", patient=None, values={})


@bp.route("/patients/<patient_id>/edit", methods=["GET", "POST"])
@protected
def patient_edit(patient_id):
    services().auth.require(token(), "patient_write")
    if request.method == "POST":
        try:
            services().patients.update(
                token(), patient_id, request.form.get("version"), **submitted_fields()
            )
        except ValidationError as exc:
            patient = services().patients.get(token(), patient_id)
            # Preserve the submitted version while invalid fields are corrected.
            return render_template(
                "patient_form.html",
                patient=patient,
                values=request.form,
                form_version=request.form.get("version"),
                error=str(exc),
            ), 400
        flash("Patient information updated.")
        return redirect(url_for("patients.patient_detail", patient_id=patient_id))
    patient = services().patients.get(token(), patient_id)
    return render_template("patient_form.html", patient=patient, values=patient)


@bp.get("/patients/<patient_id>")
@protected
def patient_detail(patient_id):
    record = services().records.get(token(), patient_id)
    return render_template(
        "patient.html",
        patient=record.patient,
        notes=record.notes,
        changes=record.changes,
    )

"""Independent note-saving and staff-reviewed category routes."""

from flask import Blueprint, flash, jsonify, redirect, request, url_for

from prs.ui.common import protected, services, token

bp = Blueprint("visits", __name__)


@bp.post("/patients/<patient_id>/notes")
@protected
def add_note(patient_id):
    services().visits.add(
        token(),
        patient_id,
        request.form.get("visit_date", ""),
        request.form.get("text", ""),
    )
    flash(
        "Visit note saved. You may now request an AI suggestion or choose a category manually."
    )
    return redirect(
        url_for("patients.patient_detail", patient_id=patient_id, _anchor="history")
    )


@bp.post("/notes/<note_id>/suggest")
@protected
def suggest(note_id):
    result = services().visits.suggest(token(), note_id)
    payload = {"status": result.status}
    if result.suggestion:
        payload.update(
            suggestion_id=result.suggestion.suggestion_id,
            category=result.suggestion.category.value,
        )
    return jsonify(payload)


@bp.post("/notes/<note_id>/review")
@protected
def review(note_id):
    note = services().visits.review(
        token(),
        note_id,
        request.form.get("suggestion_id"),
        request.form.get("decision"),
    )
    flash(
        "Suggested category accepted."
        if request.form["decision"] == "accept"
        else "Suggestion rejected. The saved category was not changed."
    )
    return redirect(
        url_for(
            "patients.patient_detail", patient_id=note.patient_id, _anchor="history"
        )
    )


@bp.post("/notes/<note_id>/category")
@protected
def manual_category(note_id):
    note = services().visits.manual_category(
        token(),
        note_id,
        request.form.get("category"),
        request.form.get("category_version"),
    )
    flash("Manual category saved.")
    return redirect(
        url_for(
            "patients.patient_detail", patient_id=note.patient_id, _anchor="history"
        )
    )

"""Small, reusable input validators."""

from datetime import date, datetime, timezone
import re

from prs.errors import ValidationError


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def clean_text(value, label: str, maximum: int, required: bool = False) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{label} must be text.")
    value = value.strip()
    if (required and not value) or len(value) > maximum or "\x00" in value:
        raise ValidationError(f"{label} must contain {'1' if required else '0'}–{maximum} characters.")
    return value


def valid_date(value: str, label: str, optional: bool = False) -> str | None:
    if optional and not value:
        return None
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValidationError(f"{label} must use YYYY-MM-DD.")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError(f"{label} must be a valid calendar date.") from exc
    if parsed > date.today():
        raise ValidationError(f"{label} cannot be in the future.")
    return parsed.isoformat()


def patient_fields(fields: dict) -> dict:
    name = clean_text(fields.get("name", ""), "Name", 120, True)
    email = clean_text(fields.get("email", ""), "Email", 254)
    phone = clean_text(fields.get("phone", ""), "Phone", 40)
    if email and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise ValidationError("Enter a valid email address.")
    if phone and (not re.fullmatch(r"[+0-9(). xX-]+", phone) or len(re.sub(r"\D", "", phone)) < 7):
        raise ValidationError("Enter a phone number with at least seven digits.")
    return dict(name=name, date_of_birth=valid_date(fields.get("date_of_birth", ""), "Date of birth", True),
                email=email, phone=phone, address=clean_text(fields.get("address", ""), "Address", 300))


def version_number(value) -> int:
    try:
        if isinstance(value, bool) or str(value) != str(int(value)) or int(value) < 0:
            raise ValueError
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError("A valid record version is required. Reload the page.") from exc

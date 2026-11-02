"""Immutable domain snapshots. All modifications go through services."""

from dataclasses import dataclass
from enum import Enum

from prs.validation import patient_fields


class Category(str, Enum):
    RESPIRATORY = "Respiratory"
    DIGESTIVE = "Digestive"
    MUSCULOSKELETAL = "Musculoskeletal"
    GENERAL = "General/Other"


@dataclass(frozen=True, slots=True)
class Patient:
    """Validated, immutable patient snapshot; stored updates return new snapshots."""

    patient_id: str
    name: str
    date_of_birth: str
    email: str
    phone: str
    address: str
    created_at: str
    updated_at: str
    version: int

    def __post_init__(self) -> None:
        """Enforce required demographics even for directly constructed objects."""
        patient_fields(
            {
                "name": self.name,
                "date_of_birth": self.date_of_birth,
                "email": self.email,
                "phone": self.phone,
                "address": self.address,
            }
        )


@dataclass(frozen=True, slots=True)
class VisitNote:
    """A permanent visit record with separately reviewed category metadata."""

    note_id: str
    patient_id: str
    visit_date: str
    text: str
    author_id: str
    created_at: str
    category: str | None
    category_source: str | None
    reviewed_by: str | None
    reviewed_at: str | None
    category_version: int


@dataclass(frozen=True, slots=True)
class StaffUser:
    """Authenticated staff identity; password hashes never enter this object."""

    user_id: str
    username: str
    role: str

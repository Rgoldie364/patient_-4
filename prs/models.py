"""Immutable domain snapshots. All modifications go through services."""

from dataclasses import dataclass
from enum import Enum


class Category(str, Enum):
    RESPIRATORY = "Respiratory"
    DIGESTIVE = "Digestive"
    MUSCULOSKELETAL = "Musculoskeletal"
    GENERAL = "General/Other"


@dataclass(frozen=True)
class Patient:
    patient_id: str
    name: str
    date_of_birth: str | None
    email: str
    phone: str
    address: str
    created_at: str
    updated_at: str
    version: int


@dataclass(frozen=True)
class VisitNote:
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


@dataclass(frozen=True)
class StaffUser:
    user_id: str
    username: str
    role: str

"""Composition root: constructs and connects the six architecture components."""

from prs.ai_integration.providers import OllamaProvider
from prs.ai_integration.service import CategorizationService
from prs.authentication.service import AuthService
from prs.patient.service import PatientService
from prs.persistence.database import Database
from prs.persistence.repositories import PatientRepository, StaffRepository, VisitRepository
from prs.visit.service import VisitService


class PRSApplication:
    def __init__(self, database_path, provider=None, ai_timeout=4.75):
        self.database = Database(database_path)
        self.database.initialize()
        self.auth = AuthService(StaffRepository(self.database))
        self.patients = PatientService(PatientRepository(self.database), self.auth)
        self.categorizer = CategorizationService(provider if provider is not None else OllamaProvider(), timeout=ai_timeout)
        self.visits = VisitService(VisitRepository(self.database), self.patients, self.auth, self.categorizer)

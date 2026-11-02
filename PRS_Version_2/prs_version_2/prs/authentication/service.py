"""Staff identity, sessions, and role-based authorization."""

import re
import secrets
import threading
import time
from uuid import uuid4

from werkzeug.security import check_password_hash, generate_password_hash

from prs.errors import AuthenticationError, AuthorizationError, ValidationError
from prs.models import StaffUser

PERMISSIONS = {
    "nurse": frozenset({"read", "patient_write", "note_write", "categorize"}),
    "doctor": frozenset({"read", "patient_write", "note_write", "categorize"}),
    "viewer": frozenset({"read"}),
    "admin": frozenset({"manage_staff"}),
}


class AuthService:
    """Passwords are hashed; opaque, expiring sessions stay on the server."""

    def __init__(self, repository, session_seconds=1800):
        self.repository = repository
        self.session_seconds = session_seconds
        self._sessions = {}
        self._attempts = {}
        self._lock = threading.Lock()
        self._dummy_hash = generate_password_hash(secrets.token_urlsafe(32))

    def provision_staff(self, username: str, password: str, role: str) -> StaffUser:
        """Local operator-only setup command; deliberately not exposed by HTTP."""
        return self._create_staff(username, password, role)

    def create_staff(
        self, token: str, username: str, password: str, role: str
    ) -> StaffUser:
        """Allow administrators to create doctor/nurse accounts through the UI."""
        actor = self.require(token, "manage_staff")
        if role not in {"doctor", "nurse"}:
            raise ValidationError(
                "Administrators may create doctor or nurse accounts here."
            )
        return self._create_staff(username, password, role, actor.user_id)

    def _create_staff(
        self, username: str, password: str, role: str, actor_id: str | None = None
    ) -> StaffUser:
        """Share validation, hashing, and persistence between bootstrap and admin UI."""
        if not isinstance(username, str) or not re.fullmatch(
            r"[A-Za-z0-9_.-]{3,50}", username
        ):
            raise ValidationError(
                "Username must be 3–50 letters, digits, periods, underscores or hyphens."
            )
        if not isinstance(password, str) or not 12 <= len(password) <= 256:
            raise ValidationError("Password must contain 12–256 characters.")
        if role not in PERMISSIONS:
            raise ValidationError("Unknown staff role.")
        user = StaffUser(str(uuid4()), username.lower(), role)
        self.repository.add(
            user.user_id,
            user.username,
            generate_password_hash(password),
            role,
            actor_id,
        )
        return user

    def login(self, username: str, password: str) -> str:
        if (
            not isinstance(username, str)
            or not isinstance(password, str)
            or len(username) > 50
            or len(password) > 256
        ):
            raise AuthenticationError("Invalid username or password.")
        username = username.strip().lower()
        now = time.monotonic()
        with self._lock:
            self._attempts = {
                k: v for k, v in self._attempts.items() if now - v[1] < 60
            }
            count, since = self._attempts.get(username, (0, now))
            if count >= 5 or len(self._attempts) >= 2000:
                raise AuthenticationError(
                    "Too many login attempts. Try again in one minute."
                )
            self._attempts[username] = (count + 1, since)
        row = self.repository.by_username(username)
        valid = check_password_hash(
            row["password_hash"] if row else self._dummy_hash, password
        )
        if not row or not row["active"] or not valid:
            raise AuthenticationError("Invalid username or password.")
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._attempts.pop(username, None)
            self._sessions = {k: v for k, v in self._sessions.items() if v[1] > now}
            if len(self._sessions) >= 2000:
                raise AuthenticationError("Session capacity reached. Try again later.")
            self._sessions[token] = (row["user_id"], now + self.session_seconds)
        return token

    def require(self, token: str | None, permission: str | None = "read") -> StaffUser:
        """Validate a session and optionally require a permission; roles are reread."""
        now = time.monotonic()
        with self._lock:
            record = self._sessions.get(token)
            if record is None or record[1] <= now:
                self._sessions.pop(token, None)
                raise AuthenticationError("Please sign in.")
        row = self.repository.by_id(record[0])
        if not row or not row["active"]:
            self.logout(token)
            raise AuthenticationError("Please sign in.")
        if permission is not None and permission not in PERMISSIONS.get(
            row["role"], ()
        ):
            raise AuthorizationError("Your staff role does not permit this operation.")
        return StaffUser(row["user_id"], row["username"], row["role"])

    def logout(self, token: str | None) -> None:
        with self._lock:
            self._sessions.pop(token, None)

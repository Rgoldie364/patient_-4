CREATE TABLE IF NOT EXISTS staff (
    user_id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('nurse','doctor','viewer')),
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1))
);
CREATE TABLE IF NOT EXISTS patients (
    patient_id TEXT PRIMARY KEY,
    name TEXT NOT NULL CHECK(length(trim(name)) > 0),
    date_of_birth TEXT,
    email TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    address TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS visit_notes (
    note_id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL REFERENCES patients(patient_id) ON DELETE RESTRICT,
    visit_date TEXT NOT NULL,
    text TEXT NOT NULL CHECK(length(trim(text)) > 0),
    author_id TEXT NOT NULL REFERENCES staff(user_id),
    created_at TEXT NOT NULL,
    category TEXT CHECK(category IN ('Respiratory','Digestive','Musculoskeletal','General/Other')),
    category_source TEXT CHECK(category_source IN ('ai_accepted','manual')),
    reviewed_by TEXT REFERENCES staff(user_id),
    reviewed_at TEXT,
    category_version INTEGER NOT NULL DEFAULT 0,
    CHECK ((category IS NULL AND category_source IS NULL AND reviewed_by IS NULL AND reviewed_at IS NULL)
        OR (category IS NOT NULL AND category_source IS NOT NULL AND reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS ix_visit_patient_date ON visit_notes(patient_id,visit_date DESC,created_at DESC);
CREATE TABLE IF NOT EXISTS audit_log (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id TEXT NOT NULL REFERENCES staff(user_id),
    action TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    details TEXT NOT NULL,
    occurred_at TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS patient_identity_immutable
BEFORE UPDATE OF patient_id, created_at ON patients BEGIN
    SELECT RAISE(ABORT, 'Patient identity is immutable');
END;
CREATE TRIGGER IF NOT EXISTS patient_no_delete
BEFORE DELETE ON patients BEGIN SELECT RAISE(ABORT, 'Patient deletion is unavailable in Version 1'); END;
CREATE TRIGGER IF NOT EXISTS visit_content_immutable
BEFORE UPDATE OF note_id, patient_id, visit_date, text, author_id, created_at ON visit_notes BEGIN
    SELECT RAISE(ABORT, 'Saved visit notes cannot be edited or moved');
END;
CREATE TRIGGER IF NOT EXISTS visit_no_delete
BEFORE DELETE ON visit_notes BEGIN SELECT RAISE(ABORT, 'Saved visit notes cannot be deleted'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_update
BEFORE UPDATE ON audit_log BEGIN SELECT RAISE(ABORT, 'Audit events are append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete
BEFORE DELETE ON audit_log BEGIN SELECT RAISE(ABORT, 'Audit events are append-only'); END;

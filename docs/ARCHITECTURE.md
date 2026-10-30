# Version 1 architecture and traceability

## Components and OOP responsibilities

| Package/class | Responsibility and key methods | Relationships |
| --- | --- | --- |
| `application.PRSApplication` | Constructs and connects the application components. | Composes one database, auth service, patient service, visit service, and categorizer. |
| `ui.web.create_app` | Flask routes, forms, sessions, CSRF protection, and rendering. | Delegates every protected use case to services. |
| `authentication.AuthService` | `provision_staff`, `login`, `require`, `logout`; password hashes, session expiry, permissions. | Uses `StaffRepository`; called by patient/visit services. |
| `models.Patient` | Frozen snapshot of patient identity and editable information. | One patient has zero or many visit notes. |
| `patient.PatientService` | `create`, `get`, `update`, `changes`; validation and allowed fields. | Uses auth and `PatientRepository`. |
| `models.VisitNote` | Frozen snapshot of a dated note and separately reviewable category. | Exactly one patient and one author; optional category reviewer. |
| `visit.VisitService` | `add`, `get`, `history`, `suggest`, `review`, `manual_category`. | Validates patients through `PatientService`; uses auth, `VisitRepository`, and optional categorizer. |
| `ai_integration.CategorizationProvider` | Abstract `suggest(note_text)` provider contract. | Implemented by `OllamaProvider`; a disabled implementation supports explicit no-AI mode. |
| `ai_integration.OllamaProvider` | Calls a real pretrained local model and validates its structured response. | Receives only note text; has no repositories, patient objects, or database credentials. |
| `ai_integration.CategorizationService` | Deadline, bounded workers, uncertainty threshold, ephemeral suggestions, one-use review tokens. | Composes a provider; stores no patient or note data persistently. |
| `persistence.Database` | Schema initialization and transaction/connection ownership. | Supplies independent SQLite connections with foreign keys enabled. |
| `StaffRepository`, `PatientRepository`, `VisitRepository` | Parameterized SQL, mapping rows to domain objects, atomic writes and audit events. | Share the database boundary. |

Encapsulation: callers cannot assign to frozen domain snapshots. Allowed edits go through explicit service methods. SQL is isolated in repositories. Database triggers independently prevent identity changes and saved-note edits/deletes. UUID4 identifiers plus primary-key uniqueness prevent duplicate stored IDs; IDs are not derived from patient names.

Abstraction and polymorphism: `CategorizationProvider` defines the interface; real, disabled, and test-only implementations can be injected without changing visit saving. Composition connects components without inheritance between unrelated business services.

## Relationships in storage

- `patients.patient_id` is the permanent primary key.
- `visit_notes.patient_id` is a required foreign key to an existing patient.
- `visit_notes.author_id` and optional `reviewed_by` reference staff users.
- `audit_log.actor_id` records the staff member responsible for each write.
- Each visit record contains one dated note in Release 1. Appointment scheduling and empty check-in records are not added; they are outside the specified note workflow.
- Patient creation/updates and their audit entries commit together. Note creation/category review and corresponding audit entries also commit together.
- Patient `version` and note `category_version` prevent stale edits from silently overwriting another staff member's changes.
- Audits track patient before/after values, note creation, accepted/manual category changes, and suggestion rejection. Read access logging is not implemented.

## Save and categorize sequence

1. UI passes the authenticated session token, patient ID, visit date, and note text to `VisitService.add`.
2. Authorization and input validation run; `PatientService.get` confirms the patient exists.
3. `VisitRepository.add` commits the note with an empty category. This path never calls AI.
4. A separate UI action requests a suggestion for that saved note.
5. The provider receives only note text. Inference returns within the application deadline or produces timeout/unavailable/uncertain status.
6. A valid suggestion lives in server memory for five minutes, bound to staff ID, note ID, and current category version. The UI labels it “Suggested category.”
7. Acceptance consumes that suggestion and saves the category with reviewer/source/time. Rejection records the decision without saving the suggested label. Staff can instead choose any of the four categories manually.
8. Failed, uncertain, expired, rejected, or late suggestions never replace an existing saved category. A newly saved uncategorized note remains uncategorized unless staff explicitly assigns a label.

## Requirement mapping

| Requirement | Version 1 implementation | Main automated evidence |
| --- | --- | --- |
| BR-01 | Browser application, protected services, durable database | Web workflow; restart test |
| UR-01 / FR-01 | UUID Patient IDs, required name, immutable object and SQL trigger | `test_ids_unique_and_immutable` |
| UR-02 / FR-03 | Exact-ID retrieval; missing record message; no changes | `test_missing_patient_no_mutation` |
| FR-04 | Explicit editable field allowlist and audited updates | `test_patient_update_and_audit`; stale-update test |
| FR-02 / FR-05 | Create a dated visit-note record only for an existing patient | `test_note_validation_and_patient_link`; orphan test |
| UR-03 / FR-06 | History ordered by visit date and isolated by patient ID | `test_history_sorted_and_isolated` |
| FR-07 | Readable patient/detail/history pages and staff forms | Flask full-web-workflow test; manual walkthrough in README |
| NFR-01 | Indexed exact-ID lookup; two-second target | Timed lookup check; local benchmark in VALIDATION.md |
| NFR-02 | Transactions, foreign keys, immutable note fields, append-only audit, concurrency versions | Foreign-key, immutability, stale-write and restart tests |
| NFR-03 | Hashed passwords, server sessions, role checks in business services, CSRF | Auth/viewer/CSRF tests |
| UR-04 / AIR-01 | Labeled ephemeral suggestion; staff accept/reject; category persists only on acceptance | Acceptance, rejection and wrong-staff/note tests |
| AIR-02 | Separate save endpoint, 4.75-second wait limit, manual category path | Save-without-AI, failure/uncertainty/late-response and real-duration timeout tests |
| Persistence | SQLite database, accounts/notes/categories/audit survive restart | Reopen/re-authenticate/retrieve test |

## Explicit Version 1 decisions

The attachments leave certain implementation choices open. These decisions are visible and configurable in a future separate version; they are not represented as verbatim approved requirements.

| Open detail | Version 1 choice |
| --- | --- |
| Exact staff permission matrix | Nurse and doctor: read/create/update patients, add/read notes, request/review/manual categories. Viewer: read records/history only. No user-facing account administration. |
| Patient editable fields | Name, birth date, email, phone, address. Only name is mandatory under the supplied requirements; contact details are optional and validated when supplied. |
| Date semantics | ISO `YYYY-MM-DD`, valid calendar dates, no future birth/visit dates. Date-only visits; audit timestamps are UTC. |
| Note mutability | Note content/date/identity/author/patient link remain fixed. Category metadata may change after explicit staff action. |
| Database topology | Local SQLite for the working demonstration instead of the diagram's separate database server. Repository isolation preserves a future replacement point. |
| AI provider | Local Ollama model, not a remote API. Default model `qwen2.5:3b`; no claim of course-specific model approval or clinical validation. |
| AI triggering | Staff selects the separate request button after saving; inference never starts inside the save transaction. |
| Session lifetime | Thirty minutes from login; no automatic renewal; all sessions end on server restart. |

The physical diagram's browser/application/database/provider separation is logical in this local deployment. This release does not implement the production HTTPS connection or a separate database server. These limitations are also stated in README.md.

# Version 2 architecture and OOP responsibilities

## Component organization

| Component | Files/classes | Responsibility |
| --- | --- | --- |
| Application composition | `application.py`: `PRSApplication` | Construct repositories and services and inject their collaborators. |
| UI | `ui/web.py`, feature Blueprints, shared handlers/common helpers, templates/static files | Present forms and records; pass requests to services; authenticate routes and validate CSRF. |
| Authentication | `authentication/service.py`: `AuthService` | Identity, password hashing, sessions, permissions, local bootstrap, and admin-authorized clinical-account creation. |
| Patient management | `models.py`: `Patient`; `patient/service.py`: `PatientService`; `patient/record.py`: `PatientRecordService` | Validate and manage patients; generate/retry IDs; assemble patient details without repeated existence queries. |
| Visit management | `models.py`: `VisitNote`; `visit/service.py`: `VisitService` | Save dated notes, validate their patient relationship, read history, and coordinate explicit category decisions. |
| AI integration | `CategorizationProvider`, `OllamaProvider`, `DisabledProvider`, `InferenceRunner`, `CategorizationService`, `SuggestionStore` | Isolate the real provider, bound inference, interpret uncertainty, and manage ephemeral review state. |
| Persistence | `Database`, `StaffRepository`, `PatientRepository`, `VisitRepository`, `schema.sql` | Connections, transactions, parameterized SQL, schema constraints/triggers, and atomic audit writes. |

The added read coordinator and AI helper classes have narrow responsibilities within existing components. They do not introduce additional architectural tiers.

## Core relationships

- One patient has zero or many visit notes. Every note has one existing patient and an author staff account, enforced by foreign keys.
- `PatientService` uses authentication and a patient repository.
- `VisitService` uses authentication, patient validation, a visit repository, and the optional categorizer. Its note-save method has no inference dependency at execution time.
- `PatientRecordService` composes patient and visit repositories for one authorized read operation.
- `CategorizationService` composes `InferenceRunner` and `SuggestionStore`. The store has no database access; the runner has no patient objects or repositories.
- `OllamaProvider` and `DisabledProvider` implement the abstract `CategorizationProvider.suggest(note_text)` contract. Test-only providers implement that same contract without claiming to be actual models.
- `AuthService.create_staff` verifies admin permission before passing validated, hashed credentials to `StaffRepository`. Clinical roles cannot self-elevate.

## Four OOP principles

| Principle | Concrete application |
| --- | --- |
| Encapsulation | Services control supported state changes. Patient IDs and note snapshots use frozen/slotted dataclasses, while SQL triggers independently reject stored identity/content changes. Suggestion dictionaries and reservations stay inside `SuggestionStore`; callers use methods instead of mutating them. |
| Abstraction | Repositories hide SQL. Services hide validation and orchestration from the UI. Provider callers use `suggest()` without knowing the HTTP request/response implementation. |
| Inheritance | Actual, disabled, and test providers inherit the abstract provider contract. Domain exceptions inherit shared error classes. Unrelated patient and note concepts do not inherit from each other. |
| Polymorphism | Inference accepts any implementation of `CategorizationProvider`. The rest of the application continues to save notes and interpret provider outcomes without changing for each provider implementation. |

Immutability protects an existing identity from normal changes. Uniqueness prevents duplicate stored IDs. Encapsulation controls the supported operations used to access/change state. These are separate properties; leading underscores or annotations alone do not guarantee them.

## Patient creation and update

1. Require the appropriate staff permission.
2. Reject fields outside the editable allowlist.
3. Normalize and validate name, mandatory birth date, and at least one contact method.
4. On create, generate a UUID-based candidate ID and attempt the patient/audit transaction. Retry only a duplicate Patient ID, up to five total attempts.
5. On update, use the existing ID as a lookup key and require the expected version. Updating demographics returns a new immutable snapshot with the same ID.

Direct `Patient` construction also validates required demographic/contact fields. Database constraints additionally reject missing DOB, missing contact, null IDs, and duplicate IDs. Calendar/email/phone format validation lives in Python. The `Patient` class alone does not guarantee unique IDs among arbitrary in-memory objects.

## Note and review sequence

1. Authorize the staff member and verify the patient exists.
2. Validate the visit date/text and save an uncategorized note and audit event atomically.
3. A separate request sends only note text to the optional provider.
4. `InferenceRunner` caps the wait at 4.75 seconds, with a maximum of four active workers. Late results cannot enter storage.
5. `CategorizationService` validates the prediction, applies the confidence threshold, and asks `SuggestionStore` to retain an acceptable suggestion in memory.
6. The UI displays **Suggested category** and requires accept/reject. Manual assignment remains available.
7. A review reserves the suggestion for the correct staff/note. After the repository commits the decision, the store consumes it. A failed transaction releases it for retry. Category versions prevent stale decisions from overwriting a newer one.

## Requirement alignment

| Requirement or revision | Implementation |
| --- | --- |
| FR-01: permanent unique Patient IDs | UUID generation, bounded collision retry, primary-key constraint, frozen snapshots, update allowlist, identity trigger. |
| FR-02/FR-05: dated visit records and notes | `VisitService.add`, valid date/nonblank note, existing-patient lookup and foreign key. |
| FR-03/FR-04/FR-06/FR-07 | Patient lookup, allowed audited updates, visit history, and browser forms. Missing IDs display Patient not found. |
| NFR-01: retrieval target | Indexed ID lookup and removal of duplicate reads. Local checks are not production performance guarantees. |
| NFR-02: integrity | Transactions, foreign keys, immutable note fields, version checks, audit records, retry-safe suggestion review. |
| NFR-03: protected records | Hashed passwords, active-account checks, roles, server-side service authorization, CSRF protections. |
| AIR-01: suggested labels need acceptance | Ephemeral suggestions plus explicit, user/note-bound staff review before storing a category. |
| AIR-02: save without AI | Separate note-save path, bounded inference wait, uncertainty/error handling, manual categories. |
| Version 2 DOB/contact revision | Shared runtime validator, domain validation, required form DOB, and database presence constraints. |
| Version 2 admin revision | Admin-only account-creation service/Blueprint; roles restricted to nurse/doctor on the web form. |
| Version separation | Distinct directory/default database; schema version guard refuses Version 1 databases. |

## Physical deployment and scope

The six logical/development components and the save-before-AI/retrieve-by-ID scenarios remain consistent with the supplied architecture. Admin account creation extends the authentication component as specifically requested for Version 2.

The local demonstration still consolidates application/database hosting and uses local HTTP. Assignment #3's separate database server and HTTPS configuration remain a documented deployment gap. No claim of a production clinical deployment is made. Sessions and pending suggestions are process-local; use a single application process. Replacing SQLite or adding distributed session storage would be separate work rather than a hidden change in this refactor.

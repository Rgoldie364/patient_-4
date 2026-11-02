# Version 2 change review

Date: November 1, 2026. Version 1 is retained as the original baseline.

## Requested findings and implemented actions

| Finding | Relevant implementation | Correction and reason | Verification |
| --- | --- | --- | --- |
| Duplicate Patient ID was not retried | `PatientService.create`; `PatientRepository.create`; `DuplicatePatientIDError` | Keep `"PAT-" + uuid4().hex`. Translate only the patients primary-key conflict into a domain error and retry up to five times. Use iteration rather than recursion so repeated collisions cannot cause an unbounded call chain. Validation and authorization occur before attempts. Failed insert/audit transactions roll back. | Force first collision then successful ID; force all five attempts to collide; force an unrelated integrity error and confirm it is not retried. |
| Birth date was optional | `Patient.date_of_birth`; `Patient.__post_init__`; `patient_fields`; patient form; schema | Change annotation to `str`, require an actual valid date at runtime, mark the form required, and add a nonnull/nonblank storage constraint. An annotation alone does not enforce validity. | Missing, null, blank, invalid and future dates are rejected; clearing a saved DOB is rejected; direct object construction and SQL null/blank tests. |
| Require at least one contact method | `patient_fields`; `Patient.__post_init__`; schema; patient form | Accept email only, phone only, or both. Reject neither, including whitespace-only input. Validate each supplied contact. Creation and updates use the same validator. Correction to the finding: Version 1 made both optional rather than requiring both. | All three valid combinations; neither; malformed supplied contact; attempted removal of last contact; email-to-phone update. |
| Need internal doctor/nurse creation | `AuthService.create_staff`; admin Blueprint; `staff_form.html`; staff repository | Add an admin role with `manage_staff`. Require that permission in the service and route. Restrict the screen to doctor/nurse creation, hash passwords, reject duplicate usernames, and audit account creation atomically. Bootstrap the first admin with a local command or demo seed. | Admin creates both roles through web requests; new users log in and survive restart; nonadmins/guests/CSRF failures denied; role tampering and weak/mismatched passwords rejected. |
| Large application factory | `ui/web.py`; `auth_routes`, `patient_routes`, `visit_routes`, `admin_routes`, `handlers`, `common` | Split routes by responsibility. Keep configuration/wiring/registration in the factory. Share CSRF, identity, and error handling instead of duplicating these in each route. Existing public URLs remain the same. | Existing web workflow and authorization checks plus new admin/patient-form regressions. |

## Related corrections from the earlier review

- **AI class responsibilities:** `InferenceRunner` handles bounded inference execution; `SuggestionStore` owns expiry, identity binding, and review reservations; `CategorizationService` interprets predictions and coordinates the two. These remain implementation details of the AI integration component.
- **Retry-safe review:** `VisitService.review()` reserves the suggestion, completes the repository transaction, and finalizes the reservation only on success. A failed acceptance or rejection can be retried until expiry. Concurrent review of the same suggestion is rejected. Existing category-version checks continue to reject stale results.
- **Error handling:** transport and malformed-model output use explicit provider exception classes. Expected and unexpected inference failures are logged by type without logging note text or raw output. Failures still leave stored notes intact. Unexpected database integrity errors are handled without exposing SQL to the UI.
- **Read optimization:** `PatientRecordService.get()` assembles the existing patient screen without calling the patient lookup three times. A traced web request performs one patient SELECT and five total SELECTs, compared with three and nine in Version 1. This avoids repeated work without removing permission checks from standalone services.
- **Storage and construction clarity:** INSERTs name their columns. `VisitNote` uses keyword arguments rather than a long positional sequence. Category updates return the record using the same connection. New/existing touched code uses consistent formatting, import organization, docstrings, and useful type annotations.
- **Encapsulation:** frozen dataclasses now use slots. Ordinary mutation remains blocked and a normal per-instance dictionary is absent. This improves accidental-state protection, not protection against arbitrary Python code with `object.__setattr__()` access.

## Code and behavior deliberately retained

`PatientService.create()` still builds each candidate using `Patient("PAT-" + uuid4().hex, ...)`. Database uniqueness is the final safeguard; UUID4 alone is not a mathematical guarantee against collisions. Existing Patient IDs are never regenerated during updates.

`VisitService.add()` still ends with `return self.repository.add(note)`. No model call occurs on this path. The note is committed before the user can request a suggestion, preserving AIR-02.

`VisitService.review()` still requires the staff member to explicitly accept or reject a suggestion. It still prevents a suggestion for another user/note or an outdated category version from being accepted. Only accepted or manually chosen categories are stored, preserving AIR-01.

The six architectural components, dated immutable notes, authorization boundaries, SQLite persistence, model adapter, four category labels, and synthetic-data-only scope remain. No messaging, appointments, password-reset system, remote AI integration, or distributed hosting features are added.

## Limits intentionally kept visible

The original deployment simplification (local HTTP and SQLite instead of HTTPS and a database server) remains documented. This refactor aligns logical responsibilities and process behavior; it does not claim that distributed deployment is complete. Live-model accuracy and visual browser rendering have separate validation limits in VALIDATION.md.

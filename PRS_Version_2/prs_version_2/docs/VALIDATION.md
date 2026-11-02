# Version 2 validation

Validation date: November 1, 2026.

## Results

| Check | Result |
| --- | --- |
| `python -m unittest discover -s tests -v` | **45 tests passed**. Full captured output: `docs/TEST_RESULTS.txt`. |
| `python -m compileall -q prs run.py evaluate_ai.py tests` | Passed. |
| `python -m ruff check .` | Passed; no remaining selected lint/import issues. |
| `python -m ruff format --check .` | Passed for all 38 Python files. |
| Demo CLI setup and repeat | Four generated staff accounts created; repeated setup preserves passwords, one patient, and one note. |
| Clean admin bootstrap | `init-admin` accepts a confirmed password, stores a usable administrator account, and does not display that password in output. |
| Admin use case | New doctor account created through the admin-authorized service after bootstrap. Web tests cover doctor and nurse creation and subsequent login. |
| Restart persistence | Patient/visit/category preservation and newly created staff login verified after constructing a fresh application against the same Version 2 database. |
| Version 1 preservation | SHA-256 checks confirm the 39 original source/delivery files plus the Version 1 ZIP are unchanged. |
| Database isolation | A Version 1-style database is refused before schema changes; its bytes remain unchanged in the regression test. |

## Regression coverage

The 25 existing tests were retained and adjusted where the newly required DOB/contact values change valid fixtures. They continue to cover frozen IDs, SQL immutability, allowed updates, patient-note links, foreign keys, history ordering, authentication, permissions, password hashes, CSRF, HTML escaping, category acceptance/rejection, stale writes, AI unavailability/uncertainty/late output, and persistence.

Twenty additional tests cover:

- A forced ID collision followed by successful retry, maximum-attempt exhaustion, and an unrelated integrity error that must not be retried. Failed transactions do not leave extra patient or audit rows.
- Required birth dates, all valid contact combinations, invalid/missing contacts, and prevention of clearing DOB or the last contact on updates. Domain and database presence constraints are checked.
- Admin-only web/service account creation, new account login and restart persistence, audit entries without passwords, rejected role escalation, duplicate usernames, mismatched/short passwords, CSRF, and anonymous/nonadmin requests.
- Required-field errors retaining submitted patient form values for correction.
- Patient-detail query count and unchanged returned content.
- Failed acceptance/rejection preserving a suggestion for retry; review reservations excluding a second review; expiry handling; diagnostic logging without note text.

## Measured read optimization

A traced Version 2 patient-detail HTTP request performs **five SELECT statements**, including **one patient lookup**. The Version 1 call chain performs nine SELECTs, including three patient lookups. The regression test asserts the Version 2 counts and that the rendered page still contains the patient's visit note.

This is a count of eliminated duplicate work, not a claim of production latency or throughput. The retained lookup test also checks the two-second local service target on a small test database.

## Limits

- The live Ollama model was not available for evaluation. Provider-contract and failure tests use clearly identified substitutes. `evaluate_ai.py` and the 16 synthetic cases are included for real-model checks on the demonstration computer.
- A Chromium browser automation attempt could not launch because this execution environment denied a required browser socket operation. **Visual rendering and interactive JavaScript were not verified in a real browser.** Flask test-client checks successfully exercise the rendered forms and HTTP workflows, including the new admin page. No browser screenshots are claimed as validation evidence.
- The local SQLite/HTTP deployment and process-local sessions/suggestions remain intentional demonstration limits. Multi-process/distributed operation and a production medical deployment are not claimed.
- The maximum 4.75-second inference wait is exercised with a deliberately slow test provider; it does not imply that an actual model will reliably finish within five seconds on all hardware.

## Local demonstration checklist

1. Extract the new archive to a separate folder and run the install/demo commands in README.md.
2. Log in as demo.admin, create a doctor and a nurse, and verify both can log in.
3. Create synthetic patients using email only, phone only, and both; demonstrate missing DOB and missing contact rejection.
4. Update permitted information and verify the Patient ID stays fixed.
5. Save and retrieve dated notes before requesting AI. Review a suggestion, reject one, and set a category manually.
6. Disable/stop AI and show that new notes still save and remain retrievable.
7. Restart PRS and retrieve the same records; verify created accounts still work.
8. Run the software tests and, when the local model is ready, the real-model evaluation.

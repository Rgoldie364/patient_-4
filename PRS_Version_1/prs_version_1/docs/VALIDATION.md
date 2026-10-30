# Version 1 validation

Validation date: October 29, 2026.

## Completed checks

- Python 3.12.14; Flask 3.1.3.
- `python -m unittest discover -s tests -v`: **25 tests passed**.
- Core test categories: ID immutability and uniqueness; allowed fields; validation; audit history; relational integrity; visit ordering; login/logout/expiry/deactivation; denied operations for viewers; hashed passwords and throttling; AI save independence; review ownership and replay prevention; stale suggestion protection; persistence after reopen.
- AI integration tests: strict output validation, note-text-only payload, rejection of remote endpoints, uncertain/error/timeout behavior, discarded late results, and bounded worker capacity.
- A real-duration test waits for the configured 4.75-second deadline with an injected provider delayed for 5.2 seconds and asserts return in under five seconds.
- Flask test-client workflow: login, patient creation, escaped HTML, note save, suggestion request, acceptance, retrieval, and logout. State-changing routes reject missing CSRF tokens.
- CLI smoke check: first demo seed, repeated seed, fresh application process, staff login, patient retrieval, and visit retrieval passed. A repeated seed preserved the original record and note.
- A 100-call authenticated lookup check against that one-patient demo database measured 0.282 ms median and 0.485 ms maximum per service lookup. This small local sample establishes functionality only, not representative scaling performance.
- Python compilation checks passed for application, entry points, and tests. A real Ollama probe returned `unavailable`, confirming the environment has no usable model endpoint.

## Validation limits

- No live Ollama model was available here. The HTTP contract and application behavior were tested with clearly marked substitutes; actual category accuracy and local-model latency have not been measured.
- `evaluate_ai.py` and 16 labeled synthetic cases are included for local evaluation. Low-confidence or unavailable responses are not counted as correct ordinary category predictions.
- Automated Chromium could not launch in this execution environment. Browser rendering, interactive JavaScript, and responsive layout were therefore not visually verified. The server-generated interface and routes passed Flask integration tests. Follow README's walkthrough in a local browser.
- The two-second lookup test measures a local service call, not a remote network or production workload. It is not a production performance guarantee.
- The demonstration uses one application process and a local SQLite database. It has not been load-tested as a distributed multi-server system.

## Submission/demo checklist

1. Install dependencies and create demo accounts; record the printed synthetic Patient ID.
2. Demonstrate create, lookup, allowed updates, and dated note/history operations.
3. Restart and retrieve the same record.
4. Sign in as a viewer and show protected writes are denied.
5. Run Ollama and demonstrate “Suggested category,” accept, reject, and manual assignment.
6. Stop/disable Ollama and show a new note saves, remains retrievable, and can be categorized manually.
7. Run all 25 software tests and the real-model evaluation on the demonstration computer.

# Patient Record System — Version 2

Python OOP coursework implementation of the PRS, revised from Version 1 according to the requested corrections. **Version 1 is preserved separately.** This folder uses its own database, `data/prs_v2.sqlite3`.

Use synthetic patient information only.

## What changed

| Requested correction | Version 2 behavior |
| --- | --- |
| Retry duplicate Patient IDs | UUID4 generation is retained. Only a Patient ID collision triggers a retry, with a maximum of five attempts. Other integrity errors are not retried. |
| Require date of birth | A nonblank, valid, nonfuture date is required on creation and update, including direct construction of a `Patient`. |
| Require at least one contact method | Email only, phone only, or both are accepted. Neither is rejected. Any contact field supplied must be valid. Version 1 actually made both optional; it did not require both. |
| Create doctors/nurses inside the application | An administrator signs in and uses the **Create staff account** screen. Doctor, nurse, and viewer accounts cannot access that operation. |
| Simplify `create_app()` | Login, patient, visit, and admin routes are separate Flask Blueprints; shared protections/error handlers have their own module. |

The required design is retained: immutable Patient IDs, protected patient operations, permanent dated notes, persistence, four AI categories, explicit staff acceptance/rejection, and note saving that does not wait for AI.

The earlier review's related issues are also addressed: AI execution and suggestion storage have separate classes; provider errors are classified and logged; patient-detail reads avoid repeated patient queries; and a failed category save retains its suggestion for retry.

## Quick start

Requirements: **Python 3.10+**, pip, and a browser. The only application dependency is Flask. SQLite and unittest are included in Python. Extract `PRS_Version_2.zip` and open a terminal inside `prs_version_2`.

### Windows PowerShell

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py seed-demo
.\.venv\Scripts\python.exe run.py serve
```

### macOS or Linux

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python run.py seed-demo
.venv/bin/python run.py serve
```

Open **http://127.0.0.1:5000**. Demo setup prints randomly generated passwords for `demo.admin`, `demo.nurse`, `demo.doctor`, and `demo.viewer`, plus one synthetic Patient ID. Save that output locally before closing the terminal; passwords are not displayed again. Repeating demo setup preserves existing passwords and data.

Commands below use `python`; substitute the virtual environment's executable above, or activate that environment first.

## Create doctor and nurse accounts through the UI

1. Sign in as **demo.admin**, using the generated password.
2. The **Create staff account** screen opens automatically.
3. Enter a unique username, choose **Doctor** or **Nurse**, and enter/confirm a password of at least 12 characters.
4. Select **Create account**. The account is saved with a password hash, and the creation is audited.
5. Sign out and sign in with the new credentials. The new account can manage patients and visit notes.

For a clean setup instead of demo accounts, bootstrap an administrator once:

```bash
python run.py init-admin clinic.admin
python run.py serve
```

The command prompts for and confirms a password without displaying it. After this initial trusted setup, create doctors and nurses in the browser. There is no unauthenticated web registration or automatic default administrator password.

The previous local operator command remains available:

```bash
python run.py create-staff doctor.smith --role doctor
```

### Permission policy

| Role | View patients/history | Create/update patients and add notes | Review/manual categories | Create doctor/nurse accounts in UI |
| --- | --- | --- | --- | --- |
| Nurse | Yes | Yes | Yes | No |
| Doctor | Yes | Yes | Yes | No |
| Viewer | Yes | No | No | No |
| Admin | No | No | No | Yes |

Admin is an account-management role. A clinical account is used for patient work. Admin creation of another admin or viewer through the web screen is deliberately excluded; the user requested doctor/nurse creation. Trusted local setup may provision any supported role.

## Patient and visit workflow

1. Sign in as a doctor or nurse and choose **New patient**.
2. Provide a fictional name, a valid date of birth, and at least one of email or phone. Address remains optional.
3. Create the patient and copy the generated `PAT-...` ID. Search by this ID to retrieve the record.
4. **Edit patient details** updates allowed fields. The ID stays fixed. Clearing date of birth or the last contact method is rejected. Moving from email-only to phone-only is allowed in one update.
5. Add a valid dated, nonblank visit note. **Save visit note** commits it immediately with no category; this method never invokes AI.
6. After saving, optionally select **Request AI suggestion**. A successful response is displayed as **Suggested category** and is not stored as the note's category yet.
7. Accept or reject it, or use the manual category dropdown. Permitted labels are Respiratory, Digestive, Musculoskeletal, and General/Other.
8. Stop and restart the server, sign in again, and retrieve the same patient. Records and accepted/manual categories persist.

Patient names need not be unique. Duplicate names receive different IDs. Saved note text, date, author, note ID, and patient relationship cannot be edited, deleted, or moved. Category metadata can change after an explicit staff decision. Stale patient edits and stale category suggestions are rejected rather than silently overwriting newer changes.

## Enable actual AI

The actual provider integration is unchanged: a pretrained local model through **Ollama**, default `qwen2.5:3b`. No keyword classifier is presented as AI. Test substitutes exist only in the automated tests.

1. Install and start Ollama: https://ollama.com/download
2. Install and warm the model:

```bash
ollama pull qwen2.5:3b
ollama run qwen2.5:3b "Reply READY"
```

3. Start PRS and request a suggestion for an already saved synthetic note. If necessary, run `ollama serve` in another terminal.

Only the note text is sent as patient-related input. The model does not receive patient IDs, contact information, database access, or tools. The application requests structured output and validates the category and uncertainty fields. Self-reported confidence below 0.75 is treated as uncertain; it is not a calibrated probability or a clinical guarantee.

The application waits at most **4.75 seconds** for inference. Model loading or slow hardware can cause a timeout. AI uncertainty, invalid output, errors, or late responses never prevent saving notes. Manual categorization remains available. Existing accepted categories are not erased by failed requests.

At most four inference workers can be active; excess requests immediately report unavailable. Suggestions remain in server memory for five minutes. They are bound to a staff user, note, and category version. A review reserves the suggestion, saves the decision and audit event, then removes it. A transient save failure releases the reservation for retry, until expiration. Restarting the server clears pending suggestions and login sessions, while preserving saved records.

### Settings

| Environment variable | Default | Purpose |
| --- | --- | --- |
| `PRS_AI` | `ollama` | Set to `disabled` to demonstrate operation without AI. |
| `PRS_OLLAMA_MODEL` | `qwen2.5:3b` | Installed local model name. |
| `PRS_OLLAMA_URL` | `http://127.0.0.1:11434` | Local HTTP endpoint; remote URLs and redirects remain disallowed. |
| `PRS_DB` | `data/prs_v2.sqlite3` within this project | Separate Version 2 database path. |

For example, in PowerShell:

```powershell
$env:PRS_AI = "disabled"
python run.py serve
```

Or macOS/Linux:

```bash
PRS_AI=disabled python run.py serve
```

An explicit database path goes before the command:

```bash
python run.py --db data/another_v2_demo.sqlite3 seed-demo
```

If port 5000 is busy, use `python run.py serve --port 5050` and open http://127.0.0.1:5050.

## Tests and evaluation

```bash
python -m unittest discover -s tests -v
python evaluate_ai.py
```

The first command runs the software regression suite. The second needs a running real model and evaluates 16 synthetic examples, reporting outcomes and latency. It is separate from the software tests. Live-model accuracy was not measured in this environment.

Optional formatting/lint checks, using the supplied configuration:

```bash
python -m pip install ruff
python -m ruff check .
python -m ruff format --check .
```

See `docs/VALIDATION.md` for results and known validation limits, `docs/CHANGES.md` for the issue-by-issue review, and `docs/ARCHITECTURE.md` for responsibilities, OOP principles, and requirements mapping.

## Keeping versions separate

- Version 1's folder/archive are preserved. Version 2 uses its own project and database.
- Startup refuses a populated database whose schema version is not 2, before changing its schema. **Do not point Version 2 at Version 1's database.**
- Existing Version 1 patients may lack the newly required birth date or contact information. No automatic import or in-place migration is included, and no missing patient information is fabricated.
- A new Version 2 database is initialized automatically. Within Version 2, repeated starts retain staff, patients, notes, categories, and audit events.
- To back up Version 2, stop the server and copy the entire `data` directory, including any SQLite sidecar files.
- The archive contains source, tests, and synthetic evaluation cases. It contains no database, credentials, environment secrets, or model weights.

## Deployment scope and architecture alignment

The logical/development components remain UI, authentication, patient management, visit management, AI integration, and persistence. Save-before-AI and explicit human review are preserved. New classes remain within those component boundaries.

This release retains the same local demonstration topology as Version 1: loopback browser HTTP, a Python application process, a SQLite file, and an optional local model process. The separate database server and HTTPS deployment in Assignment #3's physical diagram are **not implemented**. Moving to distributed hosting is a deployment project beyond the requested focused refactor. Do not describe this local release as an exact implementation of that physical diagram.

The server binds to `127.0.0.1`, runs without debug mode, and uses one application process. Session cookies are HttpOnly/SameSite, POSTs require CSRF tokens, and protected operations check permissions on the server. Database triggers protect IDs and note content. These application controls do not protect against someone with unrestricted code or database-file access. Frozen slotted dataclasses block ordinary assignment and remove the ordinary `__dict__` bypass; deliberate `object.__setattr__()` is still possible in trusted Python code and does not itself update the database.

## References

The supplied `SWE Assignment #2.pdf` and `CSCI_4490_Assignment_3_PRS_4plus1_UML(1).pdf` remain the baseline. Required birth dates, at least one contact method, and administrator account creation are the user's explicit Version 2 revisions.

- Flask Blueprints: https://flask.palletsprojects.com/en/stable/blueprints/
- Flask installation: https://flask.palletsprojects.com/en/stable/installation/
- Ollama generate API: https://docs.ollama.com/api/generate
- Local model information: https://ollama.com/library/qwen2.5:3b

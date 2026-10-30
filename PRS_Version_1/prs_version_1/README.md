# Patient Record System — Version 1

Python OOP implementation for the supplied CSCI 4490 PRS requirements and 4+1 architecture. Includes a working browser interface, staff authorization, permanent Patient IDs, dated visit notes, SQLite persistence, and staff-reviewed AI categories.

**This is a separate Version 1 project.** Keep this folder and archive intact. Put future versions in separate folders (for example, `prs_version_2`) with separate databases. This project does not modify earlier standalone patient-management programs.

Use synthetic patient information only. No real patient data is included. This is a local coursework demonstration, not a clinical deployment.

## 1. Install and start

Requirements: Python 3.10 or later, pip, and a browser. Tested with Python 3.12.14 and Flask 3.1.3. SQLite and the test framework are included with Python.

Extract `PRS_Version_1.zip`, open a terminal inside `prs_version_1`, then run:

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

Open **http://127.0.0.1:5000**. The `seed-demo` command prints three generated passwords and one synthetic Patient ID. Save them before closing the terminal. Sign in as `demo.nurse` for the complete workflow, `demo.doctor` for another editing account, or `demo.viewer` for read-only access. Demo passwords are randomly generated, not hardcoded.

The remaining examples use `python`. Substitute your virtual environment's Python path from above, or activate that environment first.

To start with an empty database and your own approved staff account instead:

```bash
python run.py init-db
python run.py create-staff nurse.ryan --role nurse
python run.py serve
```

The staff creation command prompts for a password of at least 12 characters. It is a local operator command, not a public registration endpoint. Supported roles: `nurse`, `doctor`, `viewer`. The assignment assumes the clinic supplies approved accounts; the operator provisions them here.

Stop the server with Ctrl+C. Restart with `python run.py serve`; data remains available. Sessions expire after 30 minutes and are invalidated when the server restarts, so sign in again.

If port 5000 is busy:

```bash
python run.py serve --port 5050
```

Then open http://127.0.0.1:5050.

## 2. Demonstrate the required operations

1. Sign in as a nurse or doctor.
2. Select **New patient**, enter a fictional name and optional details, then create the patient. Copy the generated `PAT-...` ID.
3. Use **Patient lookup** to find the record by that exact ID. A missing ID produces **Patient not found** without changing data.
4. Select **Edit patient details**. Name, birth date, email, phone, and address can change. The Patient ID cannot.
5. Enter a valid visit date and nonblank synthetic note. Select **Save visit note**. The note commits to the database with no category before any AI request.
6. In **Visit history**, select **Request AI suggestion**. If a suggestion arrives, it is labeled **Suggested category**. Select **Accept suggestion** or **Reject suggestion**. No suggested category enters persistent storage before acceptance.
7. Use the manual category dropdown to choose one of Respiratory, Digestive, Musculoskeletal, or General/Other. This also works when AI is unavailable, uncertain, or too slow.
8. Reload the patient record, then restart the application and retrieve it again. Details, notes, accepted/manual labels, and audit events remain saved.
9. Sign in as a viewer. Patient lookup and history work; creation, updates, note entry, and category changes are unavailable and are also denied by the server.

History is newest visit date first, with creation time and note ID breaking ties. Saved note text, visit date, author, and patient relationship cannot be edited, deleted, or moved in Version 1. Only category review metadata can change.

## 3. Enable actual AI categorization

Version 1 implements a **real local-model adapter for Ollama**, using `qwen2.5:3b` by default. There is no production keyword classifier or simulated AI. The model is installed separately because its weights are large. The app works without it and clearly reports AI unavailability.

1. Install Ollama from https://ollama.com/download and start the Ollama application/service.
2. Download the model:

```bash
ollama pull qwen2.5:3b
```

3. Warm the model before demonstrating the five-second requirement:

```bash
ollama run qwen2.5:3b "Reply READY"
```

4. Start PRS and request a suggestion on an already saved note. If your installation requires manually starting the Ollama server, use `ollama serve` in a separate terminal.

The adapter calls `http://127.0.0.1:11434/api/generate` with a JSON response schema. Only note text is sent as patient-related input. Patient IDs, names, contact details, other notes, and database access are not given to the model. Use fictional note text even when the model runs locally.

The model may return one of the four labels or uncertainty. Results below the 0.75 confidence threshold are treated as uncertain. This is the model's self-reported confidence, not a calibrated probability or a guarantee of accuracy. The prompt requests record organization only; the model does not diagnose or recommend treatment.

The application stops waiting after **4.75 seconds**, within the five-second requirement. Slow model loading or limited hardware can cause timeouts. The saved note remains intact, and late model results are discarded. At most four inference workers run concurrently; excess requests immediately receive an unavailable result. Pending suggestions expire after five minutes and on application restart.

To use a different local model, set `PRS_OLLAMA_MODEL` before starting PRS. Example PowerShell:

```powershell
$env:PRS_OLLAMA_MODEL = "qwen2.5:3b"
```

Example macOS/Linux:

```bash
export PRS_OLLAMA_MODEL=qwen2.5:3b
```

Optional settings:

| Setting | Default | Purpose |
| --- | --- | --- |
| `PRS_AI` | `ollama` | Set to `disabled` to demonstrate normal operation with AI turned off. |
| `PRS_OLLAMA_MODEL` | `qwen2.5:3b` | Installed local model name. |
| `PRS_OLLAMA_URL` | `http://127.0.0.1:11434` | Loopback HTTP endpoint only; remote endpoints and redirects are rejected. |
| `PRS_DB` | `data/prs_v1.sqlite3` in this project | Explicit path to the Version 1 database. |

Run the real-model evaluation after installing and warming Ollama:

```bash
python evaluate_ai.py
```

It prints the model result, expected result, status, and latency for 16 synthetic cases. It also reports suggestion coverage and expected-outcome match rate, counting outages and timeouts as unsuccessful cases. These are classroom examples, not a clinical validation set. No live-model accuracy result was obtained during development in this workspace.

## 4. Run software tests

```bash
python -m unittest discover -s tests -v
```

The included 25 tests verify identities, validation, relationships, history, permissions, password storage, CSRF, escaped HTML, stale updates, AI acceptance/rejection, failure/uncertainty/timeout handling, the HTTP adapter contract, and reopening the database. Test-only providers are explicitly labeled substitutes and are never used by `run.py`.

See `docs/VALIDATION.md` for the recorded results and limitations. See `docs/ARCHITECTURE.md` for class responsibilities, relationships, assumptions, and requirement mapping.

## 5. Data and version separation

- Persistent data is stored in `data/prs_v1.sqlite3`, created automatically on first run. Staff passwords are stored as salted hashes.
- `seed-demo` does not reset an existing demo account's password or overwrite its records. A second invocation preserves the first demo dataset.
- The archive includes source code and synthetic evaluation cases; it does not contain a populated database, passwords, model weights, or environment secrets.
- To copy the database for a backup, stop PRS first and copy the whole `data` directory, including any SQLite sidecar files. Keep backups with Version 1.
- Future versions should use their own project directory and database. Do not point a new version at this database without a deliberate migration.

## 6. Architecture scope

The six logical/development components and save-before-AI sequence follow the attached diagrams. The browser and Python server run locally for this deliverable. **SQLite consolidates the diagram's separate database server into a local file**, and the local browser connection uses HTTP. The optional AI provider is another local process. This is a documented coursework deployment simplification; a separate database server, HTTPS deployment, distributed sessions, and production operational controls are not implemented.

The server binds only to loopback and runs without debug mode. Use a single application process: sessions and unaccepted suggestions are intentionally in memory. Database triggers and service permissions protect application operations; a person with direct write access to the database file remains outside that boundary.

## 7. Source documents and API references

Assignment source documents supplied by the user:

- `SWE Assignment #2.pdf`: pp. 2–6 (scope, rules, functional/nonfunctional and AI requirements); pp. 7–8 (traceability).
- `CSCI_4490_Assignment_3_PRS_4plus1_UML(1).pdf`: pp. 1–5 (logical, process, development, physical, and scenario views).

Implementation references checked October 29, 2026:

- Flask installation: https://flask.palletsprojects.com/en/stable/installation/
- Flask quickstart: https://flask.palletsprojects.com/en/stable/quickstart/
- Ollama generate API: https://docs.ollama.com/api/generate
- Model details and license: https://ollama.com/library/qwen2.5:3b

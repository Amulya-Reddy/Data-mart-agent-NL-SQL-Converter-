# Data Mart Agent: NL - SQL- Converter Agent


A natural-language query agent for an anesthesia billing/reconciliation data
mart. Type a question in plain English, and Claude answers it by writing and
running SQL against the data — showing you exactly what it ran, so every
answer is auditable.

This is a **prototype for a project-approval demo**. It runs entirely on
synthetic, fictional data with zero setup beyond an Anthropic API key — no
real database, no PHI, no cloud credentials required.

## Architecture

```
Web UI (static HTML/JS)  ─┐
                           ├──> FastAPI backend ──> data_source switch ──> demo DB (SQLite) [prototype]
Teams bot (Bot Framework) ─┘                                          └─> Fabric SQL endpoint [production, later]
```

One backend agent (`backend/agent.py`), two front ends. The data backend is
swappable via `DATA_SOURCE=demo|fabric` without touching the agent, the API,
or either UI — `backend/data_source.py` dispatches to `sqlite_source.py`
(the demo) or `fabric_client.py` (stubbed for production) behind an identical
`run_query(sql)` / `get_schema()` interface. SQL safety rules live once, in
`backend/sql_guardrails.py`, and are shared by both backends.

## 5-minute setup

Requires Python 3.10+.

```bash
# 1. Create a virtualenv and install dependencies
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# edit .env and set ANTHROPIC_API_KEY=sk-ant-...

# 3. Seed the synthetic data mart (fully fictional, fixed random seed)
python demo_data/seed_demo_data.py
# prints row counts + referential integrity checks; should end with
# "All integrity checks passed."

# 4. Start the backend
uvicorn backend.main:app --reload --port 8000
# confirm it's up: curl http://localhost:8000/api/health

# 5. Open the web UI
open frontend/index.html
# (or serve it: python -m http.server 8080 --directory frontend)
```

The web UI talks to the backend via `window.MART_API_BASE`, set at the top of
`frontend/index.html` (default `http://localhost:8000`). If the backend runs
somewhere else, edit that line.

If `ANTHROPIC_API_KEY` is unset, the backend still runs and `/api/ask`
returns a clearly-labeled mocked response instead of erroring — useful for
checking the plumbing before you have a key.

### Running the Teams bot (optional)

```bash
python teams_bot/app.py
# listens on :3978, forwards every message to the backend's /api/ask
```

Registering a real Azure Bot resource (App ID/password, Teams channel, app
manifest) is a manual Azure Portal / Teams admin center step — this code only
implements the bot logic and message adapter. See "Path to production" below.

## The synthetic dataset

`demo_data/seed_demo_data.py` builds a local SQLite file (`demo_data/ncap_demo.db`)
with a dim/fact model, fully **fictional** data, fixed random seed
(reproducible — no real patients, providers, or claims anywhere).

| Table | Rows | Represents |
|---|---|---|
| `dim_Facility` | 4 | The four fictional facilities (Riverview Hospital, St. Pinewood Medical Center, Lakeside Surgical Center, Westbrook Medical Center). |
| `dim_Provider` | ~22 | Surgeons (2–3 per facility, varied specialties), anesthesiologists, and CRNAs. |
| `dim_Payer` | 8 | Insurance payers: 5 commercial (Aetna, BCBS, UnitedHealthcare, Cigna, Humana), Medicare, Medicaid, Self-Pay. |
| `dim_Patient` | 500 | Patient roster — insurance mix weighted toward commercial + Medicare/Medicaid, small self-pay slice. Contains identifying fields (name, DOB, MRN); the agent is instructed to avoid pulling these unless the question requires identity. |
| `fact_Schedule` | 1,000 | Scheduled OR cases — mostly Completed, with a realistic minority of Cancelled / No-Show / future-Scheduled. |
| `fact_Surgery` | ~750–800 | The case/incident anchor table. One row per completed schedule entry: surgeon, anesthesia provider, ASA class, anesthesia CPT code (00100–01999 range, matched to surgeon specialty), start/end times. |
| `fact_Billing` | ~1,500+ | Charge/Payment/Adjustment transaction lines per completed case. Charge − Paid − Adjustment reconciles to $0 for fully resolved (Paid/Denied) claims. |
| `fact_Claims` | ~750–800 | One claim per completed case — status (Paid/Pending/Denied/Submitted/Appealed), billed/allowed/paid amounts, and CARC-style denial codes (CO-50, CO-16, PR-1, etc.) on denied/appealed claims. |

Re-run the seed script any time to regenerate the file — it's idempotent
(deletes and recreates `ncap_demo.db`) and always produces the same data
thanks to the fixed seed.

## Good demo questions

These are pre-filled as clickable examples in the web UI:

- *"What is our claim denial rate by payer?"*
- *"What is the average time from claim submission to payment?"*
- *"Which procedures generate the highest average charge?"*
- *"How many cases are currently unbilled or have an outstanding balance?"*

Other questions that showcase the schema well:

- *"Which facility has the most cancelled or no-show cases?"*
- *"What's the breakdown of ASA class across all completed surgeries?"*
- *"Which surgeon has the highest volume of orthopedic cases?"*
- *"What are the most common denial reasons?"*

Every answer comes with a collapsible **Receipt** panel showing the exact SQL
the agent ran and how many rows it got back — click it to verify the answer
yourself.

## Path to production

This prototype deliberately sidesteps the hard parts of a production
deployment by using synthetic data. Moving to a real Fabric-backed data mart
means addressing all of the following:

**Data layer**
- Implement `backend/fabric_client.py` for real: replace the lazy `pyodbc` +
  `azure-identity` stub with a tested connection pool, retry logic, and error
  handling against the actual Fabric SQL endpoint.
- Point `DATA_SOURCE=fabric` and populate the `FABRIC_*` / `AZURE_*` env vars.
- Validate the real Fabric schema against what `get_schema()` returns — table
  and column names, types, and relationships may differ from this demo's
  dim/fact model.

**HIPAA / compliance — becomes live the moment this touches real patient data**
The synthetic-data approach in this prototype sidesteps every one of these;
none of them are addressed by the current code:
- **BAA with Anthropic.** A Business Associate Agreement must be in place
  before any real PHI is sent to the Claude API.
- **PHI minimization.** The current system prompt *asks* Claude to avoid
  pulling identifying fields — that's a soft guardrail, not enforcement. In
  production, consider column-level access controls or views that exclude
  direct identifiers by default, with identity lookups requiring an explicit,
  audited escalation path.
- **Audit logging.** The prototype records queries in-memory per request
  (returned in the API response) but does not persist them. Production needs
  durable, tamper-evident logging of every question asked, every query run,
  and who asked it.
- **Access control.** No authentication exists on the API or the Teams bot
  today. Production needs per-user auth, role-based access (e.g., billing
  staff vs. clinical staff see different data), and session-level audit
  trails tied to identity.
- **Data residency / encryption.** Confirm Fabric and Anthropic API traffic
  meet your organization's data residency and encryption-in-transit/at-rest
  requirements.

**Guardrails hardening**
- The current SQL guardrail (`backend/sql_guardrails.py`) is a regex-based
  read-only check — sufficient for a demo, but consider a dedicated read-only
  DB role/credential as defense in depth, plus query cost/complexity limits
  for a large production warehouse.
- Add row-level security if different users should see different facilities
  or payers.

**Operational**
- Add real authentication to `/api/ask` and `/api/health`.
- Rate limiting and cost controls on the Claude API calls.
- Structured logging/observability (currently none beyond FastAPI defaults).
- Real Azure Bot resource registration for the Teams bot (App ID/password,
  channel registration, manifest packaging, and Teams admin center approval)
  — all manual steps outside this codebase.
- Replace the static HTML/JS web frontend with whatever hosting/build
  pipeline your organization standardizes on, if needed at scale.

## Tech stack

Python 3 / FastAPI backend &middot; plain HTML/JS/CSS frontend (no build
step) &middot; Bot Framework SDK + aiohttp for Teams &middot; SQLite for the
demo data layer &middot; `anthropic` Python SDK for the agent loop.

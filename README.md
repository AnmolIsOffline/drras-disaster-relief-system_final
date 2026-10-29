# DRRAS — Disaster Relief Resource Allocation System

DRRAS is a Django application with 11 connected HTML pages and a responsive vanilla JavaScript interface. Local development uses SQLite and the existing `db.sqlite3` file.

## Run locally

Python 3.11 or newer is recommended. From PowerShell in the project directory:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

Open http://127.0.0.1:8000/. The seed command creates or updates clearly marked fictional demo records and can be rerun. Migrations update the existing database; there is no reset or reseed command that deletes its data. To inspect the app without seeded accounts, run migrations and create an administrator with `python manage.py createsuperuser`.

The checked-in `.env.example` documents optional local settings. Django uses SQLite at `db.sqlite3`; no external database service or database URL is used.

## Demo accounts

Seeded accounts use `ReliefDemo2026!`. The Maharashtra sample accounts include `admin@drras.demo`, `official@drras.demo`, `sahyog@drras.demo`, `seva@drras.demo`, `volunteer@drras.demo`, `volunteer2@drras.demo`, `volunteer3@drras.demo`, `ngo.volunteer@drras.demo`, `driver@drras.demo`, and `citizen@drras.demo`. Additional drivers, volunteers, citizens, and two pending applicants are available for workflow demonstrations. Punjab accounts use `punjab.` email prefixes; responder accounts are associated with their respective Government or NGO rosters.

## Data and SQLite behavior

The application persists users and approvals, emergencies and acceptance history, responder assignments, dispatches and vehicle trips, shelters, inventory and stock movements, funds and demonstration donations, broadcasts, notifications, support tickets, reports, and audit history. `python manage.py seed_demo` reconciles its fictional sample records without deleting their history. Active responder assignments and vehicle dispatches have database uniqueness constraints. Emergency acceptance uses an atomic conditional update, so only one competing organization can change an open emergency to accepted.

SQLite allows only one writer at a time and does not provide row-level `SELECT FOR UPDATE` locking. Under write contention an operation may return a conflict response; refresh and retry after the other write finishes. The uniqueness constraints and conditional transitions protect the key assignment and acceptance invariants, but SQLite is intended here for local development and modest workloads.

Donations remain in demonstration mode; no payment provider is connected. Live GPS tracking is not included. Map tiles and fonts currently load from public CDNs, so those assets require internet access.

## Verification

Run the operations test suite with:

```powershell
python manage.py test operations
```

Other useful checks:

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py showmigrations
```

The tests cover authentication and registration, approval boundaries, acceptance competition, volunteer and driver allocation, dispatch and delivery updates, inventory and fund rules, shelter capacity, notifications, reports and CSV exports, page rendering, and repeatable seeding.

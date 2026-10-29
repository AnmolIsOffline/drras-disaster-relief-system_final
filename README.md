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

The repository includes `work/python`, a Windows Python 3.12 snapshot of the installed packages for this workspace. It is optional and platform-specific; the virtual environment and `requirements.txt` above remain the supported setup. Temporary browser output and crash data under `work/tmp` are not included.

The checked-in `db.sqlite3` is a fictional demo snapshot; its temporary login sessions are cleared before publishing. Do not put real personal or operational data in this database or commit a locally populated replacement. The checked-in `.env.example` documents optional local settings. Django uses SQLite at `db.sqlite3`; no external database service or database URL is used.

## Local account reference

All accounts below are fictional local login identities for this application. Password for every seeded account: `PunjabRelief2026!`. Email addresses are login identifiers and do not receive mail. The Government applicant and NGO coordinator marked **PENDING** still require approval.

### Administrator

- Harpreet Singh — `harpreet.singh.admin@drras.local`

### Citizens

- Amritpal Singh — `amritpal.singh.citizen01@drras.local`
- Jasleen Kaur — `jasleen.kaur.citizen02@drras.local`
- Gurkirat Singh — `gurkirat.singh.citizen03@drras.local`
- Simranjit Kaur — `simranjit.kaur.citizen04@drras.local`
- Dilpreet Singh — `dilpreet.singh.citizen05@drras.local`
- Navjot Kaur — `navjot.kaur.citizen06@drras.local`
- Arshdeep Singh — `arshdeep.singh.citizen07@drras.local`
- Kiranpreet Kaur — `kiranpreet.kaur.citizen08@drras.local`
- Harman Singh — `harman.singh.citizen09@drras.local`
- Manpreet Kaur — `manpreet.kaur.citizen10@drras.local`
- Prabhjot Singh — `prabhjot.singh.citizen11@drras.local`
- Sandeep Kaur — `sandeep.kaur.citizen12@drras.local`
- Rupinder Singh — `rupinder.singh.citizen13@drras.local`
- Amanpreet Kaur — `amanpreet.kaur.citizen14@drras.local`
- Lakhwinder Singh — `lakhwinder.singh.citizen15@drras.local`
- Ravneet Kaur — `ravneet.kaur.citizen16@drras.local`
- Jatinder Singh — `jatinder.singh.citizen17@drras.local`
- Taranjit Kaur — `taranjit.kaur.citizen18@drras.local`
- Kuldeep Singh — `kuldeep.singh.citizen19@drras.local`
- Rajwinder Kaur — `rajwinder.kaur.citizen20@drras.local`
- Eknoor Singh — `eknoor.singh.citizen21@drras.local`
- Balpreet Kaur — `balpreet.kaur.citizen22@drras.local`
- Gagandeep Singh — `gagandeep.singh.citizen23@drras.local`
- Sukhdeep Kaur — `sukhdeep.kaur.citizen24@drras.local`
- Inderjit Singh — `inderjit.singh.citizen25@drras.local`
- Pavneet Kaur — `pavneet.kaur.citizen26@drras.local`
- Balwinder Kaur — `balwinder.kaur.citizen27@drras.local`
- Harleen Kaur — `harleen.kaur.citizen28@drras.local`
- Satnam Singh — `satnam.singh.citizen29@drras.local`
- Jasbir Kaur — `jasbir.kaur.citizen30@drras.local`
- Gurleen Kaur — `gurleen.kaur.citizen31@drras.local`
- Tejinder Singh — `tejinder.singh.citizen32@drras.local`
- Parminder Kaur — `parminder.kaur.citizen33@drras.local`
- Kirandeep Singh — `kirandeep.singh.citizen34@drras.local`
- Jagdeep Kaur — `jagdeep.kaur.citizen35@drras.local`
- Amandeep Singh — `amandeep.singh.citizen36@drras.local`
- Ranjit Kaur — `ranjit.kaur.citizen37@drras.local`
- Gurpreet Kaur — `gurpreet.kaur.citizen38@drras.local`
- Harjot Singh — `harjot.singh.citizen39@drras.local`
- Nimrat Kaur — `nimrat.kaur.citizen40@drras.local`
- Birinder Singh — `birinder.singh.citizen41@drras.local`

### Government Officials

- Gurpreet Singh — `gurpreet.singh.gov.official@drras.local`
- Navdeep Singh — `navdeep.singh.gov.official@drras.local` — **PENDING approval**
- Jaskaran Singh — `jaskaran.singh.gov.official@drras.local`

### Government Volunteers

- Amritpal Kaur — `amritpal.kaur.gov.volunteer01@drras.local`
- Sukhdeep Singh — `sukhdeep.singh.gov.volunteer02@drras.local`
- Dilpreet Kaur — `dilpreet.kaur.gov.volunteer03@drras.local`
- Mandeep Singh — `mandeep.singh.gov.volunteer04@drras.local`
- Raghav Singh — `raghav.singh.gov.volunteer05@drras.local`
- Charanjit Kaur — `charanjit.kaur.gov.volunteer06@drras.local`

### Government Drivers

- Sukhwinder Singh — `sukhwinder.singh.gov.driver01@drras.local`
- Maninder Singh — `maninder.singh.gov.driver02@drras.local`
- Jasleen Singh — `jasleen.singh.gov.driver03@drras.local`

### NGO Coordinators

- Simran Kaur — `simran.kaur.ngo.coordinator@drras.local`
- Amandeep Brar — `amandeep.brar.ngo.coordinator@drras.local`
- Manpreet Gill — `manpreet.gill.ngo.coordinator@drras.local` — **PENDING approval**
- Kirandeep Gill — `kirandeep.gill.ngo.coordinator@drras.local`
- Jaspreet Kaur — `jaspreet.kaur.ngo.coordinator@drras.local`

### NGO Volunteers

- Harsimran Kaur — `harsimran.kaur.ngo.volunteer01@drras.local`
- Gurleen Singh — `gurleen.singh.ngo.volunteer02@drras.local`
- Prabhjot Kaur — `prabhjot.kaur.ngo.volunteer03@drras.local`
- Baljinder Singh — `baljinder.singh.ngo.volunteer04@drras.local`
- Simranjit Singh — `simranjit.singh.ngo.volunteer05@drras.local`
- Rupinder Kaur — `rupinder.kaur.ngo.volunteer06@drras.local`
- Lovepreet Singh — `lovepreet.singh.ngo.volunteer07@drras.local`
- Gagandeep Kaur — `gagandeep.kaur.ngo.volunteer08@drras.local`
- Jasdeep Singh — `jasdeep.singh.ngo.volunteer09@drras.local`
- Kirat Kaur — `kirat.kaur.ngo.volunteer10@drras.local`

### NGO Drivers

- Ravinder Singh — `ravinder.singh.ngo.driver01@drras.local`
- Navjot Gill — `navjot.gill.ngo.driver02@drras.local`
- Balpreet Singh — `balpreet.singh.ngo.driver03@drras.local`
- Tavleen Kaur — `tavleen.kaur.ngo.driver04@drras.local`

## Data and SQLite behavior

The application persists users and approvals, emergencies and acceptance history, responder assignments, dispatches and vehicle trips, shelters, inventory and stock movements, funds and demonstration donations, broadcasts, notifications, support tickets, reports, and audit history. `python manage.py seed_demo` reconciles its fictional sample records without deleting their history. Active responder assignments and vehicle dispatches have database uniqueness constraints. Emergency acceptance uses an atomic conditional update, so only one competing organization can change an open emergency to accepted.

SQLite allows only one writer at a time and does not provide row-level `SELECT FOR UPDATE` locking. Under write contention an operation may return a conflict response; refresh and retry after the other write finishes. The uniqueness constraints and conditional transitions protect the key assignment and acceptance invariants, but SQLite is intended here for local development and modest workloads.

Donations remain in demonstration mode; no payment provider is connected. Live GPS tracking is not included. Map tiles and fonts currently load from public CDNs, so those assets require internet access.

## Render deployment preparation

The repository includes `build.sh` for Render's build command. Configure the web service to run `bash build.sh` and start it with `python -m gunicorn drras.wsgi:application --bind 0.0.0.0:$PORT`. The project uses WhiteNoise for collected static files. Set `DJANGO_DEBUG=0`, a unique `DJANGO_SECRET_KEY` of at least 50 characters, `ALLOWED_HOSTS` to the Render hostname, and `TRUST_X_FORWARDED_PROTO=1` in the service environment. Keep `DEMO_PAYMENT_MODE=1` for the demonstration deployment.

The app still uses SQLite at `db.sqlite3` and stores uploaded delivery photos under `media/`. Render's free service has ephemeral storage, so its SQLite data and photos can disappear after restart, redeploy, or spin-down. Persistent use requires a persistent disk and changing the configured database and media paths to that disk, or moving to durable managed storage. Do not treat the free service as a durable deployment for this data.

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

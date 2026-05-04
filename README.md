# health-connect-web-app

A personal **health portfolio** I can share with my doctors, friends, and family.

Samsung Health Connect on my phone aggregates data from all my health apps (MacroFactor, Fitbod, Samsung Health, hospital FHIR, etc.) and exports a zipped SQLite snapshot to Google Drive on a schedule. This app:

1. Pulls the latest export from Drive (daily Cloud Run Job).
2. Reads the SQLite, upserts into Cloud SQL Postgres.
3. Serves a small FastAPI site with tabs for **Overview**, **General Health**, **Food**, and **Supplements & Drugs**, gated by Google OAuth + email allowlist.

> Sensitive data: every page is allowlisted. Sharing is invitation-only.

## What's on each page

- **Overview**: 4 headline cards (BP 7d avg, Weight 7d avg, Resting HR 30d avg, Steps 30d avg, each anchored to the most recent reading) + a "Daily Micronutrients (food + supplements)" table that sums avg food intake against my supplement stack and compares both to FDA Daily Value and IOM Upper Limits.
- **General Health**: latest readings, charts (BP, weight, steps, calories burned, RHR), recent workouts and sleep tables.
- **Food**: macros chart with a 7/14/30/60/90/180-day window picker, daily-detail table, average daily micros vs % DV, top-logged items. All food windows anchor to my most recent food log so the page stays useful between syncs.
- **Supplements & Drugs**: filterable table of my stack (search + supplement/drug chips) plus a Daily Value tally panel showing total daily intake from supplements vs DV and UL.

## Architecture

```text
[ phone: Health Connect ] --(zip)--> [ Google Drive ]
                                            |
                       (cron: daily) [ Cloud Scheduler ]
                                            |
                                            v
                            [ Cloud Run Job: hcw-sync ]
                                            |
                                            v
                            [ Cloud SQL: Postgres 16 ]
                                            ^
                                            |
                            [ Cloud Run Service: hcw-web ]
                                            |
                            (Google OAuth + email allowlist)
                                            |
                                            v
                                       Joe + invitees
```

Same container image runs both tiers; the Job overrides `command` to `hcw-sync`.

## Local development

### Prerequisites

- Python 3.11+
- A Google OAuth web client (Cloud Console > APIs & Services > Credentials, type "Web application")
  with redirect URI `http://localhost:8000/auth/callback`.

### Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
copy .env.example .env  # fill in GOOGLE_OAUTH_CLIENT_ID / SECRET, ALLOWED_EMAILS
```

### Sync data into the local SQLite dev DB

```powershell
.\.venv\Scripts\python.exe -m health_connect_web.sync --local .\health_connect_export.db
```

This creates `hcw.db` (the app's persistent store, not the Health Connect export) and upserts blood pressure, heart rate, steps, weight, body fat, height, calories, distance, floors, elevation, exercise sessions, sleep, and nutrition. A per-record sanity cap drops obvious upstream data-entry mistakes (e.g. thiamin entered as grams instead of milligrams).

### Seed supplements & drugs

```powershell
copy vitamins.toml.example vitamins.toml
# edit vitamins.toml with the items I take (see comments in the file for field meanings)
.\.venv\Scripts\python.exe scripts\seed_vitamins.py
```

Each item's optional `contributes = { zinc_mg = 30 }` map drives the Daily Value tally on /supplements and the combined-intake table on the Overview page. Field keys match `_DV_INFO` in [`src/health_connect_web/web/queries.py`](src/health_connect_web/web/queries.py).

### Run the web app

```powershell
.\.venv\Scripts\python.exe -m uvicorn health_connect_web.web.app:app --host 127.0.0.1 --port 8000
# Open http://localhost:8000
```

Templates and CSS hot-reload (Jinja's `auto_reload` + static-file revalidation), so editing a `.html` or `.css` file just needs a browser refresh. Python edits require a server restart.

### Run tests

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m black --check .
```

### One-time Drive OAuth (for production sync)

Download an OAuth Desktop client JSON to `.secrets/drive_credentials.json`, then:

```powershell
.\.venv\Scripts\python.exe scripts\bootstrap_drive_oauth.py
```

Writes `.secrets/drive_token.json`. That JSON gets uploaded to Secret Manager (`hcw-drive-token`) for the Cloud Run Job to use.

## Deployment

GCP infrastructure is in [`infra/`](infra/) (Terraform, GCS-backed state). The pattern mirrors my [homebase-gcal-integration](../homebase-gcal-integration) project:

- Artifact Registry repo `containers` for images.
- Cloud SQL Postgres (smallest enterprise tier) for persistence.
- Cloud Run Service (`hcw-web`) for the FastAPI app, public + app-level allowlist.
- Cloud Run Job (`hcw-sync`) invoked by Cloud Scheduler daily.
- Secret Manager for session secret, DB password, OAuth client secret, Drive token JSON.
- Workload Identity Federation pool for **GitLab CI** (no long-lived JSON keys).

CI is **not yet wired up**. Terraform creates the `gitlab-deployer` SA and OIDC pool so GitLab runs *can* deploy when the `.gitlab-ci.yml` is filled in.

### One-time bootstrap

```bash
# Create the GCS state bucket (outside Terraform, chicken-and-egg).
gcloud storage buckets create gs://health-connect-web-tfstate --location=us-west1

cd infra
terraform init
terraform apply
```

After the first apply:

```bash
# Push the OAuth client secret as a new Secret Manager version.
echo -n "<oauth-client-secret>" | gcloud secrets versions add hcw-google-oauth-client-secret --data-file=-

# Push the Drive token JSON.
gcloud secrets versions add hcw-drive-token --data-file=.secrets/drive_token.json

# Build and push the first image, then update the Run service/job to point at it.
gcloud auth configure-docker us-west1-docker.pkg.dev
docker build -t us-west1-docker.pkg.dev/health-connect-web/containers/hcw-web:v1 .
docker push us-west1-docker.pkg.dev/health-connect-web/containers/hcw-web:v1
gcloud run services update hcw-web --region us-west1 --image us-west1-docker.pkg.dev/health-connect-web/containers/hcw-web:v1
gcloud run jobs update hcw-sync --region us-west1 --image us-west1-docker.pkg.dev/health-connect-web/containers/hcw-web:v1

# Trigger the first sync manually before relying on the daily cron.
gcloud run jobs execute hcw-sync --region us-west1
```

### Required GitLab CI variables (when CI is wired up)

| Name                         | Value                                                                  |
| ---------------------------- | ---------------------------------------------------------------------- |
| `GCP_PROJECT_ID`             | `health-connect-web`                                                   |
| `GCP_WORKLOAD_IDENTITY_POOL` | `projects/<num>/locations/global/workloadIdentityPools/gitlab-pool/providers/gitlab-provider` |
| `GCP_DEPLOYER_SA`            | `gitlab-deployer@<project>.iam.gserviceaccount.com`                    |

## Project layout

```text
src/health_connect_web/
  config.py              # env-driven settings (pydantic)
  db.py                  # SQLAlchemy engine/session
  models.py              # all persistent tables (incl. JSON daily_contrib on Vitamin)
  units.py               # ms-epoch -> datetime, g -> kg, etc.
  sync/
    drive.py             # pull latest export from Drive
    extract.py           # open Health Connect SQLite, yield typed records
                         # incl. NUTRITION_FIELDS unit conversion + sanity caps
    load.py              # upsert into our DB (idempotent on uuid, chunked)
    runner.py            # orchestrate
    __main__.py          # `hcw-sync` CLI
  web/
    app.py               # FastAPI app factory + routes
    auth.py              # Google OAuth + email allowlist
    queries.py           # read queries; FDA DV / UL data lives here in _DV_INFO
    __main__.py          # `hcw-web` uvicorn entrypoint
  templates/             # Jinja: base, login, forbidden, index, health, food, supplements
  static/                # style.css, charts.js (food chart), vitamins.js (supplements filter)
scripts/
  bootstrap_drive_oauth.py   # one-time: write Drive token to .secrets/
  seed_vitamins.py           # idempotent: vitamins.toml -> Vitamin table
infra/
  main.tf, variables.tf, outputs.tf
  artifact_registry.tf, cloud_sql.tf, secret_manager.tf
  cloud_run_service.tf, cloud_run_job.tf, cloud_scheduler.tf
  service_accounts.tf, gitlab_oidc.tf
```

## Roadmap

- [ ] Wire up `.gitlab-ci.yml` (build + push, terraform plan/apply, deploy).
- [ ] Alembic migrations (currently using `Base.metadata.create_all`).
- [ ] Add a "Labs" tab that reads `medical_resource_table` (FHIR data from UCSD).
- [ ] HTMX-driven date-range pickers on more charts (food's macros chart already has one).
- [ ] Backup verification: weekly assertion that `hcw-sync` actually wrote rows.

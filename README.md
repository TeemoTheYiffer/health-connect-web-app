# health-connect-web-app

A personal **health portfolio** I can share with my doctors, friends, and family.

Samsung Health Connect on my phone aggregates data from all my health apps (MacroFactor, Fitbod, Samsung Health, hospital FHIR, etc.) and exports a zipped SQLite snapshot to Google Drive on a schedule. This app:

1. Pulls the latest export from Drive (daily Cloud Run Job).
2. Reads the SQLite, upserts into Cloud SQL Postgres.
3. Serves a small FastAPI site at `https://hcw-web-1093810433932.us-west1.run.app`, gated by Google OAuth + email allowlist, with tabs for **Overview**, **General Health**, **Food**, **Supplements**, **Teas**, and **Schedule**.

> Sensitive data: every page is allowlisted. Sharing is invitation-only.

## What's on each page

- **Overview** — 4 headline cards (BP 7d avg, Weight 7d avg, Resting HR 30d avg, Steps 30d avg, each anchored to the most recent reading), a **Data Freshness** panel showing latest record + days-behind per table (catches "sync ran but data didn't advance" cases), a **Daily Micronutrients (food + supplements)** table that sums avg food intake against my supplement stack vs FDA Daily Value and IOM Upper Limit, and a **Download export (.md)** button that grabs a Markdown summary for sharing with a doctor or pasting into Claude / ChatGPT for review.
- **General Health** — latest readings, charts (BP, weight, steps, calories burned, RHR), recent workouts and sleep tables.
- **Food** — macros chart with a 7/14/30/60/90/180-day window picker, daily-detail table, average daily micros vs % DV, top-logged items. All food windows anchor to my most recent food log so the page stays useful between syncs.
- **Supplements & Drugs** — filterable table of my stack (search + supplement / drug chips) plus a Daily Value tally panel showing total daily intake from supplements vs DV and UL. Driven by [`vitamins.toml`](vitamins.toml).
- **Teas** — herbal-tea ingredient table at the *ingredient* level so a prescriber can scan for herb-drug interactions (CYP3A4 inhibitors, GABAergic sedation stacking, warfarin INR concerns, antihypertensive additivity, etc.). Below the table, brewing protocols for my morning + nighttime brews. Driven by [`teas.toml`](teas.toml).
- **Schedule** — daily supplement / training-day / rest-day protocol with timing rationale, caffeine rules, and key pairings. Driven by [`schedule.toml`](schedule.toml).

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

Same container image runs both tiers; the Job overrides `command` to `hcw-sync`. Drive auth uses the runtime service account (folder shared with `hcw-sync-runner@...`); no OAuth user-token to expire every 7 days.

## Curated content (TOML, edit freely)

| File | Drives | Notes |
| --- | --- | --- |
| [`vitamins.toml`](vitamins.toml) | `/supplements` table + DV tally + Overview combined-intake | Each item's `contributes = { zinc_mg = 30 }` map feeds into `_DV_INFO` in [`queries.py`](src/health_connect_web/web/queries.py) |
| [`teas.toml`](teas.toml) | `/teas` ingredient table (DB-backed) **and** the brewing-protocols section (read at request time from the `[brewing]` block) | One file, two consumers |
| [`schedule.toml`](schedule.toml) | `/schedule` page | Pure narrative content, read at request time |

The hcw-sync Cloud Run Job reseeds the supplement + herb tables from `vitamins.toml` + `teas.toml` on every run, including **reconciliation** — items removed from the TOML are deleted from the DB. Defensive: if a TOML parses to zero items the reconcile is skipped (so a parse error doesn't wipe the table).

## Local development

### Prerequisites

- Python 3.11+
- A Google OAuth web client (Cloud Console > APIs & Services > Credentials, type "Web application") with redirect URI `http://localhost:8000/auth/callback`.

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

This creates `hcw.db` (the app's persistent store, not the Health Connect export) and:

- Upserts blood pressure, heart rate, steps, weight, body fat, height, calories, distance, floors, elevation, exercise sessions, sleep, and nutrition.
- Applies per-record sanity caps that drop obvious upstream data-entry mistakes (e.g. thiamin entered as grams instead of milligrams).
- Seeds the Vitamin and Herb tables from `vitamins.toml` and `teas.toml` (idempotent, reconciling).
- Migrates schema where needed (e.g. widens older `VARCHAR(128)` columns to `TEXT`).

### Run the web app

```powershell
.\.venv\Scripts\python.exe -m uvicorn health_connect_web.web.app:app --host 127.0.0.1 --port 8000
# Open http://localhost:8000
```

Templates and CSS hot-reload (Jinja's `auto_reload` + static-file revalidation), so editing a `.html`, `.css`, or any of the three TOML content files just needs a browser refresh. Python edits require a server restart.

### Run tests

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m black --check .
```

### One-time Drive OAuth (local dev only)

For local development we use an OAuth user-token (matches the dev convenience pattern). Production uses a service account share on the Drive folder, no token needed.

Download an OAuth Desktop client JSON to `.secrets/drive_credentials.json`, then:

```powershell
.\.venv\Scripts\python.exe scripts\bootstrap_drive_oauth.py
```

Writes `.secrets/drive_token.json`. The sync code prefers this file when present (local dev) and falls back to ADC otherwise (Cloud Run + the SA share).

## Deployment

### Production setup

GCP infrastructure is in [`infra/`](infra/) (Terraform, GCS-backed state):

- Artifact Registry repo `containers` for images.
- Cloud SQL Postgres for persistence.
- Cloud Run Service (`hcw-web`) for the FastAPI app, public + app-level allowlist.
- Cloud Run Job (`hcw-sync`) invoked by Cloud Scheduler daily.
- Secret Manager for session secret, DB password, OAuth client secret.
- Workload Identity Federation pool for **GitLab CI** (no long-lived JSON keys).
- Drive folder shared with the `hcw-sync-runner` SA (no token in Secret Manager).

### CI/CD (wired up)

Pushes to `main` trigger `.gitlab-ci.yml`:

1. **lint** — `ruff check --fix .` + `black .` (apply-mode, doesn't block on drift).
2. **test** — `pytest`.
3. **build** — `gcloud builds submit --tag $IMAGE:$CI_COMMIT_SHORT_SHA .` (Cloud Build).
4. **deploy** — `gcloud run services/jobs update --image $IMAGE:$CI_COMMIT_SHORT_SHA` for both `hcw-web` and `hcw-sync`.

End-to-end ~5 minutes from merge to live. Auth uses GitLab OIDC tokens exchanged at Google STS for impersonation of the `gitlab-deployer` SA — no JSON keys anywhere. Image is tagged with the commit SHA so rollbacks are `gcloud run services update --image $IMAGE:<older-sha>`.

### Manual deploy (escape hatch)

If CI is broken, deploy from PowerShell:

```powershell
$tag = (git rev-parse --short HEAD)
$img = "us-west1-docker.pkg.dev/health-connect-web-app/containers/hcw-web:$tag"

gcloud builds submit --tag $img .
gcloud run services update hcw-web --region us-west1 --image $img --quiet
gcloud run jobs update hcw-sync  --region us-west1 --image $img --quiet
Write-Host "Deployed $tag"
```

Requires `gcloud auth application-default login` to be current.

### Infra changes (terraform apply)

Deliberately **local-only**, not in CI. `terraform apply` needs broad IAM (Cloud SQL admin, Secret Manager admin, IAM admin) and can destroy resources if a TF file is wrong. When you change anything under `infra/`:

```powershell
cd infra
terraform apply
```

Review the plan, type `yes`.

### Trigger a sync immediately

The sync job runs daily on Cloud Scheduler. Trigger one manually:

```powershell
gcloud run jobs execute hcw-sync --region us-west1
```

### One-time bootstrap (for a fresh GCP project)

```powershell
# 1. Create the GCS state bucket (outside Terraform, chicken-and-egg).
gcloud storage buckets create gs://health-connect-web-tfstate --location=us-west1

# 2. First terraform apply creates everything but Cloud Run (because the image doesn't exist yet).
cd infra
terraform init
terraform apply

# 3. Build + push the first image.
cd ..
gcloud builds submit --tag us-west1-docker.pkg.dev/health-connect-web-app/containers/hcw-web:v1 .

# 4. Re-apply terraform so Cloud Run can provision against the now-existing image.
cd infra
terraform apply

# 5. Push the OAuth client secret (extract from the JSON downloaded from Cloud Console).
$secret = (Get-Content ..\.secrets\hcw-local.json | ConvertFrom-Json).web.client_secret
$secret | Out-File -Encoding utf8NoBOM ..\.secrets\_oauth_secret.tmp
gcloud secrets versions add hcw-google-oauth-client-secret --data-file=..\.secrets\_oauth_secret.tmp
Remove-Item ..\.secrets\_oauth_secret.tmp

# 6. Share the Drive folder containing Health Connect zips with hcw-sync-runner@<project>.iam.gserviceaccount.com (Viewer).

# 7. Add the prod Cloud Run URL to your OAuth client's Authorized redirect URIs.

# 8. Trigger the first sync manually.
gcloud run jobs execute hcw-sync --region us-west1
```

## Project layout

```text
src/health_connect_web/
  config.py              # env-driven settings (pydantic-settings)
  db.py                  # SQLAlchemy engine/session
  models.py              # all persistent tables (Vitamin, Herb, SyncRun, sync record tables)
  units.py               # ms-epoch -> datetime, g -> kg, etc.
  sync/
    drive.py             # ADC-first Drive auth + download latest export
    extract.py           # open Health Connect SQLite, yield typed records.
                         # NUTRITION_FIELDS does unit conversion + per-record sanity caps.
    load.py              # upsert into our DB (idempotent on uuid, chunked for SQLite)
    supplements.py       # idempotent + reconciling seed of Vitamin and Herb tables from TOML
    runner.py            # orchestrate
    __main__.py          # `hcw-sync` CLI: schema-migrate + seed + sync
  web/
    app.py               # FastAPI app factory + routes
    auth.py              # Google OAuth + email allowlist
    content.py           # request-time TOML loaders for /schedule and /teas brewing
    exports.py           # /export.md Markdown summary for doctors / LLM review
    queries.py           # read queries; FDA DV / UL data lives here in _DV_INFO
    __main__.py          # `hcw-web` uvicorn entrypoint (proxy_headers=True for Cloud Run TLS)
  templates/             # Jinja: base, login, forbidden, index, health, food,
                         # supplements, teas, schedule
  static/                # style.css, charts.js, vitamins.js
scripts/
  bootstrap_drive_oauth.py   # one-time local: write Drive token to .secrets/
  seed_vitamins.py           # one-shot local: vitamins.toml -> Vitamin table
                             # (prod uses the in-job seed instead)
vitamins.toml              # supplements + drugs (TOML)
teas.toml                  # herbal ingredients + brewing protocols (TOML)
schedule.toml              # daily timing protocol (TOML)
infra/
  main.tf, variables.tf, outputs.tf
  artifact_registry.tf, cloud_sql.tf, secret_manager.tf
  cloud_run_service.tf, cloud_run_job.tf, cloud_scheduler.tf
  service_accounts.tf, gitlab_oidc.tf
.gitlab-ci.yml             # lint, test, build, deploy (OIDC auth, no JSON keys)
```

## Roadmap

- [ ] Alembic migrations (currently using `Base.metadata.create_all` plus ad-hoc `ALTER COLUMN` in the sync job).
- [ ] Add a "Labs" tab that reads `medical_resource_table` (FHIR data from UCSD).
- [ ] HTMX-driven date-range pickers on more charts (food's macros chart already has one).
- [ ] Backup verification: weekly assertion that `hcw-sync` actually wrote rows.
- [ ] Migrate the dev Drive flow to ADC + SA impersonation too, so the local OAuth-token bootstrap step goes away entirely.
- [ ] Split infra into "safe" (Cloud Run, Scheduler) and "guarded" (SQL, IAM) modules so the safe parts can auto-apply in CI.

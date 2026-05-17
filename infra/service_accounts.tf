# Three runtime SAs + one deployer SA. Mirrors the homebase-gcal pattern, with the addition
# of a separate web-service SA so the web tier can be scoped to read Cloud SQL only,
# and the sync job retains permission to also read Drive (token JSON is in Secret Manager).

resource "google_service_account" "web" {
  account_id   = "hcw-web-runner"
  display_name = "Cloud Run Service runtime SA for hcw-web"
}

resource "google_service_account" "sync" {
  account_id   = "hcw-sync-runner"
  display_name = "Cloud Run Job runtime SA for hcw-sync"
}

resource "google_service_account" "scheduler" {
  account_id   = "hcw-scheduler"
  display_name = "Cloud Scheduler invoker SA for hcw-sync"
}

resource "google_service_account" "deployer" {
  account_id   = "gitlab-deployer"
  display_name = "GitLab CI deployer SA"
}

# --- Cloud SQL connectivity for both tiers ---

resource "google_project_iam_member" "web_cloudsql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.web.email}"
}

resource "google_project_iam_member" "sync_cloudsql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.sync.email}"
}

# --- Secret Manager access (per-secret bindings live in secret_manager.tf) ---

# --- Deployer permissions (CI) ---

# Push container images.
resource "google_project_iam_member" "deployer_artifact_writer" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.deployer.email}"
}

# Submit Cloud Build jobs (the CI pipeline calls `gcloud builds submit`).
resource "google_project_iam_member" "deployer_cloudbuild_editor" {
  project = var.project_id
  role    = "roles/cloudbuild.builds.editor"
  member  = "serviceAccount:${google_service_account.deployer.email}"
}

# Cloud Build uploads source to gs://<project>_cloudbuild before building.
resource "google_project_iam_member" "deployer_storage_admin" {
  project = var.project_id
  role    = "roles/storage.admin"
  member  = "serviceAccount:${google_service_account.deployer.email}"
}

# Cloud Build runs builds as a service account; let the deployer impersonate it.
resource "google_project_iam_member" "deployer_sa_user_project" {
  project = var.project_id
  role    = "roles/iam.serviceAccountUser"
  member  = "serviceAccount:${google_service_account.deployer.email}"
}

# Manage Cloud Run revisions (service + job).
resource "google_project_iam_member" "deployer_run_admin" {
  project = var.project_id
  role    = "roles/run.admin"
  member  = "serviceAccount:${google_service_account.deployer.email}"
}

# Read project state during `terraform plan`.
resource "google_project_iam_member" "deployer_viewer" {
  project = var.project_id
  role    = "roles/viewer"
  member  = "serviceAccount:${google_service_account.deployer.email}"
}

# Allow deployer to attach the runtime SAs to the Run revisions it deploys.
resource "google_service_account_iam_member" "deployer_act_as_web" {
  service_account_id = google_service_account.web.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.deployer.email}"
}

resource "google_service_account_iam_member" "deployer_act_as_sync" {
  service_account_id = google_service_account.sync.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.deployer.email}"
}

# Cloud Scheduler invoker rights are scoped to the specific job in cloud_scheduler.tf.

# Cloud SQL admin actions (creating users, etc.) are managed by Terraform with the
# project owner, not the deployer SA. Keeps the deployer's blast radius small.

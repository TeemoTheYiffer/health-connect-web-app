# Cloud Run Job: the daily Drive -> Postgres sync.
# Same image as the web service, just a different CMD via `args`.
#
# Drive auth: the runtime SA `hcw-sync-runner` accesses the Drive folder via ADC.
# The folder must be shared with the SA's email (Viewer role) for reads to work.
# This sidesteps the 7-day refresh-token expiry that bites OAuth user creds in apps
# that haven't gone through Google's verification process.

resource "google_cloud_run_v2_job" "sync" {
  name                = local.job_name
  location            = var.region
  deletion_protection = false

  template {
    template {
      service_account = google_service_account.sync.email
      timeout         = "900s"
      max_retries     = 1

      volumes {
        name = "cloudsql"
        cloud_sql_instance {
          instances = [local.cloud_sql_connection_name]
        }
      }

      containers {
        image   = local.sync_image
        command = ["hcw-sync"]

        env {
          name  = "APP_ENV"
          value = "prod"
        }
        env {
          name  = "LOG_LEVEL"
          value = var.log_level
        }
        env {
          name  = "DRIVE_FOLDER_ID"
          value = var.drive_folder_id
        }
        env {
          name = "DATABASE_URL"
          value = "postgresql+psycopg://${local.cloud_sql_user}@/${local.cloud_sql_database}?host=/cloudsql/${local.cloud_sql_connection_name}"
        }
        env {
          name = "PGPASSWORD"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.db_password.secret_id
              version = "latest"
            }
          }
        }

        volume_mounts {
          name       = "cloudsql"
          mount_path = "/cloudsql"
        }

        resources {
          limits = {
            cpu    = "1"
            memory = "1Gi"
          }
        }
      }
    }
  }

  depends_on = [
    google_artifact_registry_repository.containers,
    google_sql_database.hcw,
    google_secret_manager_secret_version.db_password,
  ]
}

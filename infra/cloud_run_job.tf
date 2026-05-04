# Cloud Run Job: the daily Drive -> Postgres sync.
# Same image as the web service, just a different CMD via `args`.

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

      volumes {
        name = "drive-token"
        secret {
          secret = google_secret_manager_secret.drive_token.secret_id
          items {
            version = "latest"
            path    = "drive_token.json"
            mode    = 0o400
          }
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
          name  = "DRIVE_TOKEN_JSON_PATH"
          value = "/secrets/drive/drive_token.json"
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
        volume_mounts {
          name       = "drive-token"
          mount_path = "/secrets/drive"
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

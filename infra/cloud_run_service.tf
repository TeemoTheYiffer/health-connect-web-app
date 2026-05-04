# Cloud Run Service: the FastAPI web app.
# Connects to Cloud SQL via the built-in auth proxy (Unix socket at /cloudsql/<connection_name>).

resource "google_cloud_run_v2_service" "web" {
  name     = local.service_name
  location = var.region

  deletion_protection = false

  template {
    service_account = google_service_account.web.email
    timeout         = "60s"

    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [local.cloud_sql_connection_name]
      }
    }

    containers {
      image = local.web_image

      ports {
        container_port = 8080
      }

      env {
        name  = "APP_ENV"
        value = "prod"
      }
      env {
        name  = "LOG_LEVEL"
        value = var.log_level
      }
      env {
        name  = "OWNER_EMAIL"
        value = var.owner_email
      }
      env {
        name  = "ALLOWED_EMAILS"
        value = join(",", var.allowed_emails)
      }
      env {
        name  = "GOOGLE_OAUTH_CLIENT_ID"
        value = var.google_oauth_client_id
      }
      env {
        name = "DATABASE_URL"
        # Unix-socket form for the Cloud SQL Auth Proxy.
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
      env {
        name = "SESSION_SECRET"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.session_secret.secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "GOOGLE_OAUTH_CLIENT_SECRET"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.google_oauth_client_secret.secret_id
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
          memory = "512Mi"
        }
        cpu_idle          = true
        startup_cpu_boost = true
      }

      startup_probe {
        http_get { path = "/healthz" }
        initial_delay_seconds = 5
        period_seconds        = 5
        failure_threshold     = 6
      }

      liveness_probe {
        http_get { path = "/healthz" }
        period_seconds = 30
      }
    }
  }

  depends_on = [
    google_artifact_registry_repository.containers,
    google_sql_database.hcw,
    google_secret_manager_secret_version.session_secret,
    google_secret_manager_secret_version.db_password,
  ]
}

# Public access. Allowlist gating happens inside the app (Google OAuth + email allowlist).
resource "google_cloud_run_v2_service_iam_member" "web_public" {
  name     = google_cloud_run_v2_service.web.name
  location = google_cloud_run_v2_service.web.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}

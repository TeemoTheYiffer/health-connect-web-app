# Cloud SQL Postgres for the synced health data + curated content.
# Smallest practical Enterprise-edition shape; bump to db-custom-2-* if read load grows.

resource "google_sql_database_instance" "hcw" {
  name             = local.cloud_sql_instance
  database_version = "POSTGRES_16"
  region           = var.region

  # Allow Terraform `destroy` to actually remove the instance during early development.
  # FLIP TO TRUE before going to production with real data Joe cares about.
  deletion_protection = false

  settings {
    tier              = "db-custom-1-3840"
    edition           = "ENTERPRISE"
    availability_type = "ZONAL"
    disk_type         = "PD_SSD"
    disk_size         = 10
    disk_autoresize   = true

    backup_configuration {
      enabled                        = true
      start_time                     = "08:00" # UTC
      point_in_time_recovery_enabled = true
      backup_retention_settings {
        retained_backups = 7
        retention_unit   = "COUNT"
      }
    }

    ip_configuration {
      # Public IP, but Cloud Run connects through the Cloud SQL Auth Proxy (not the public address).
      ipv4_enabled    = true
      ssl_mode        = "ENCRYPTED_ONLY"
      # No authorized networks. All access goes via the auth proxy + IAM.
    }

    insights_config {
      query_insights_enabled  = true
      record_application_tags = true
      record_client_address   = false
    }
  }

  depends_on = [google_project_service.services]
}

resource "google_sql_database" "hcw" {
  name     = local.cloud_sql_database
  instance = google_sql_database_instance.hcw.name
}

resource "random_password" "app_db" {
  length  = 32
  special = false # avoid characters that need URL-escaping in DATABASE_URL
}

resource "google_sql_user" "app" {
  name     = local.cloud_sql_user
  instance = google_sql_database_instance.hcw.name
  password = random_password.app_db.result
}

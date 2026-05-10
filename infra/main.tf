terraform {
  required_version = ">= 1.9"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  backend "gcs" {
    bucket = "health-connect-web-tfstate"
    prefix = "infra"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

locals {
  service_name      = "hcw-web"
  job_name          = "hcw-sync"
  artifact_repo     = "containers"
  artifact_repo_url = "${var.region}-docker.pkg.dev/${var.project_id}/${local.artifact_repo}"
  web_image         = "${local.artifact_repo_url}/${local.service_name}:${var.image_tag}"
  sync_image        = "${local.artifact_repo_url}/${local.service_name}:${var.image_tag}" # same image, different CMD

  cloud_sql_instance = "hcw-db"
  cloud_sql_database = "hcw"
  cloud_sql_user     = "hcw_app"

  # Connection name format: <project>:<region>:<instance>
  cloud_sql_connection_name = "${var.project_id}:${var.region}:${local.cloud_sql_instance}"
}

# Enable required APIs. Idempotent.
resource "google_project_service" "services" {
  for_each = toset([
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudscheduler.googleapis.com",
    "sqladmin.googleapis.com",
    "secretmanager.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "compute.googleapis.com",
    "drive.googleapis.com", # for the sync job's SA to read the Drive folder
  ])
  service            = each.key
  disable_on_destroy = false
}

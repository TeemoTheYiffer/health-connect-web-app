output "web_service_url" {
  description = "Public URL of the Cloud Run web service."
  value       = google_cloud_run_v2_service.web.uri
}

output "sync_job_name" {
  description = "Cloud Run Job name (for `gcloud run jobs execute ...`)."
  value       = google_cloud_run_v2_job.sync.name
}

output "cloud_sql_connection_name" {
  description = "Cloud SQL connection name (used in DATABASE_URL via the auth proxy)."
  value       = local.cloud_sql_connection_name
}

output "artifact_registry_url" {
  description = "Where CI should push container images."
  value       = local.artifact_repo_url
}

output "deployer_service_account_email" {
  description = "SA that GitLab CI impersonates via Workload Identity."
  value       = google_service_account.deployer.email
}

output "workload_identity_provider" {
  description = "Full provider resource path for GitLab CI's `google-github-actions/auth`-style step."
  value       = google_iam_workload_identity_pool_provider.gitlab.name
}

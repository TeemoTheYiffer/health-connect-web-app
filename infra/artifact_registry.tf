resource "google_artifact_registry_repository" "containers" {
  location      = var.region
  repository_id = local.artifact_repo
  description   = "Container images for the health-connect-web app (web service + sync job)."
  format        = "DOCKER"

  depends_on = [google_project_service.services]
}

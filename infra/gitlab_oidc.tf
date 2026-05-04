# GitLab CI -> GCP via Workload Identity Federation (no long-lived JSON keys).
# Reference: https://docs.gitlab.com/ee/ci/cloud_services/google_cloud/

resource "google_iam_workload_identity_pool" "gitlab" {
  workload_identity_pool_id = "gitlab-pool"
  display_name              = "GitLab CI"
  description               = "OIDC pool for GitLab CI deploys"
}

resource "google_iam_workload_identity_pool_provider" "gitlab" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.gitlab.workload_identity_pool_id
  workload_identity_pool_provider_id = "gitlab-provider"
  display_name                       = "GitLab.com OIDC"

  attribute_mapping = {
    "google.subject"           = "assertion.sub"
    "attribute.project_path"   = "assertion.project_path"
    "attribute.namespace_path" = "assertion.namespace_path"
    "attribute.ref"            = "assertion.ref"
    "attribute.ref_type"       = "assertion.ref_type"
  }

  # Lock to this exact GitLab project so other tenants on gitlab.com can't impersonate the deployer.
  attribute_condition = "assertion.project_path == \"${var.gitlab_project_path}\""

  oidc {
    issuer_uri = "https://gitlab.com"
  }
}

# Allow CI runs from var.gitlab_project_path to impersonate the deployer SA.
resource "google_service_account_iam_member" "gitlab_can_impersonate_deployer" {
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.gitlab.name}/attribute.project_path/${var.gitlab_project_path}"
}

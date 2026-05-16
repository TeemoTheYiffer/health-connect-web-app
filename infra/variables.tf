variable "project_id" {
  description = "GCP project ID hosting the app."
  type        = string
  default     = "health-connect-web-app"
}

variable "region" {
  description = "GCP region for Cloud Run, Artifact Registry, Cloud SQL, Cloud Scheduler."
  type        = string
  default     = "us-west1"
}

variable "image_tag" {
  description = "Container image tag to deploy. CI passes the git SHA."
  type        = string
  default     = "latest"
}

variable "cron_schedule" {
  description = "Cloud Scheduler cron expression for the daily sync."
  type        = string
  default     = "0 7 * * *"
}

variable "timezone" {
  description = "Timezone for the cron schedule and the app's time math."
  type        = string
  default     = "America/Los_Angeles"
}

variable "log_level" {
  description = "Python logging level for both the web service and the sync job."
  type        = string
  default     = "INFO"
}

variable "gitlab_project_path" {
  description = "GitLab project path allowed to assume the deployer SA via OIDC. e.g. TeemoTheYiffer/health-connect-web-app"
  type        = string
  default     = "TeemoTheYiffer/health-connect-web-app"
}

variable "owner_email" {
  description = "Email of the site owner, implicitly always allowed and has admin rights."
  type        = string
  default     = "joeaguirre0@gmail.com"
}

variable "allowed_emails" {
  description = "Additional emails allowed to view the site (Google OAuth allowlist). Owner is implicit."
  type        = list(string)
  default     = ["joeaguirre0@yahoo.com", "joeaguirre@khatnid.com", "catnip447@gmail.com", "zoepepe02@gmail.com"]
}

variable "drive_folder_id" {
  description = "Google Drive folder ID containing Health Connect export zips."
  type        = string
  default     = "1xsLGjjeZEFI7CtAl2rjrv-ul2oC05XmM"
}

variable "google_oauth_client_id" {
  description = "OAuth client ID for the web app's Google sign-in. Public value (not a secret) so it lives in source."
  type        = string
  default     = "1093810433932-8hbn9b035vcrtledn21bcg7jffapl5rj.apps.googleusercontent.com"
}

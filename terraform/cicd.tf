# __generated__ by Terraform
# Please review these resources and move them into your main configuration files.

locals {
  # GitHub connection + linked repo are created manually (OAuth); see the resource ledger
  github_repo = "projects/${var.project_id}/locations/${var.region}/connections/github/repositories/ibozkurt79-billing-assistant-agent"
}

# App pipeline: on push to main run cloudbuild.yaml (tests -> evals -> build -> deploy) as cicd-sa
resource "google_cloudbuild_trigger" "deploy_main" {
  project         = var.project_id
  location        = var.region
  name            = "deploy-main"
  filename        = "cloudbuild.yaml"
  service_account = google_service_account.cicd.id
  disabled        = false

  # Don't rebuild/redeploy the app when only infrastructure code changes
  ignored_files = ["terraform/**"]

  repository_event_config {
    repository = local.github_repo
    push {
      branch = "^main$"
    }
  }
}

# Infra pipeline: on push to main touching terraform/, run terraform plan as terraform-sa (read-only)
resource "google_cloudbuild_trigger" "infra_main" {
  project         = var.project_id
  location        = var.region
  name            = "infra-main"
  filename        = "terraform/cloudbuild-infra.yaml"
  service_account = google_service_account.terraform.id

  # Only infrastructure changes start this pipeline (the mirror of deploy_main's ignored_files)
  included_files = ["terraform/**"]

  repository_event_config {
    repository = local.github_repo
    push {
      branch = "^main$"
    }
  }
}

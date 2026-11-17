
# __generated__ by Terraform from "projects/gen-lang-client-0223243806/locations/us-central1/repositories/cloud-run-source-deploy"
resource "google_artifact_registry_repository" "cloud_run_images" {
  description            = "Cloud Run Source Deployments"
  format                 = "DOCKER"
  location               = var.region
  mode                   = "STANDARD_REPOSITORY"
  project                = var.project_id
  repository_id          = "cloud-run-source-deploy"
  cleanup_policy_dry_run = true # report only; switch to false after checking the logs

  # Never delete the 10 newest images (live revision + recent rollbacks)
  cleanup_policies {
    id     = "keep-latest-10"
    action = "KEEP"
    most_recent_versions {
      keep_count = 10
    }
  }

  # Delete images older than 30 days, unless the KEEP rule protects them
  cleanup_policies {
    id     = "delete-older-than-30d"
    action = "DELETE"
    condition {
      tag_state  = "ANY"
      older_than = "2592000s" # 30 days
    }
  }
  lifecycle {
    prevent_destroy = true # deleting the repo deletes every image Cloud Run revisions point to
  }
}

# __generated__ by Terraform from "projects/gen-lang-client-0223243806/locations/us-central1/repositories/cloud-run-source-deploy roles/artifactregistry.writer serviceAccount:cicd-sa@gen-lang-client-0223243806.iam.gserviceaccount.com"
resource "google_artifact_registry_repository_iam_member" "cicd_writer" {
  location   = var.region
  member     = google_service_account.cicd.member
  project    = var.project_id
  repository = google_artifact_registry_repository.cloud_run_images.name
  role       = "roles/artifactregistry.writer"
}

# __generated__ by Terraform from "projects/gen-lang-client-0223243806/serviceAccounts/billing-bot-sa@gen-lang-client-0223243806.iam.gserviceaccount.com"
resource "google_service_account" "billing_bot" {
  account_id      = "billing-bot-sa"
  deletion_policy = "DELETE"
  disabled        = false
  display_name    = "Billing bot runtime"
  project         = var.project_id
  lifecycle {
    prevent_destroy = true
  }
}

# __generated__ by Terraform from "projects/gen-lang-client-0223243806/serviceAccounts/billing-bot-sa@gen-lang-client-0223243806.iam.gserviceaccount.com roles/iam.serviceAccountUser serviceAccount:cicd-sa@gen-lang-client-0223243806.iam.gserviceaccount.com"
resource "google_service_account_iam_member" "cicd_act_as_billing_bot" {
  member             = google_service_account.cicd.member
  role               = "roles/iam.serviceAccountUser"
  service_account_id = google_service_account.billing_bot.name
}

# __generated__ by Terraform from "projects/gen-lang-client-0223243806/serviceAccounts/cicd-sa@gen-lang-client-0223243806.iam.gserviceaccount.com"
resource "google_service_account" "cicd" {
  account_id      = "cicd-sa"
  deletion_policy = "DELETE"
  disabled        = false
  display_name    = "CI/CD pipeline (Cloud Build)"
  project         = var.project_id
  lifecycle {
    prevent_destroy = true
  }
}

# __generated__ by Terraform from "gen-lang-client-0223243806 roles/aiplatform.user serviceAccount:billing-bot-sa@gen-lang-client-0223243806.iam.gserviceaccount.com"
resource "google_project_iam_member" "billing_bot_aiplatform_user" {
  member  = google_service_account.billing_bot.member
  project = var.project_id
  role    = "roles/aiplatform.user"
}

# __generated__ by Terraform from "gen-lang-client-0223243806 roles/aiplatform.user serviceAccount:cicd-sa@gen-lang-client-0223243806.iam.gserviceaccount.com"
resource "google_project_iam_member" "cicd_aiplatform_user" {
  member  = google_service_account.cicd.member
  project = var.project_id
  role    = "roles/aiplatform.user"
}


# __generated__ by Terraform from "gen-lang-client-0223243806 roles/run.developer serviceAccount:cicd-sa@gen-lang-client-0223243806.iam.gserviceaccount.com"
resource "google_project_iam_member" "cicd_run_developer" {
  member  = google_service_account.cicd.member
  project = var.project_id
  role    = "roles/run.developer"
}

# __generated__ by Terraform from "gen-lang-client-0223243806 roles/bigquery.jobUser serviceAccount:cicd-sa@gen-lang-client-0223243806.iam.gserviceaccount.com"
resource "google_project_iam_member" "cicd_bigquery_job_user" {
  member  = google_service_account.cicd.member
  project = var.project_id
  role    = "roles/bigquery.jobUser"
}

# __generated__ by Terraform from "gen-lang-client-0223243806 roles/bigquery.jobUser serviceAccount:billing-bot-sa@gen-lang-client-0223243806.iam.gserviceaccount.com"
resource "google_project_iam_member" "billing_bot_bigquery_job_user" {
  member  = google_service_account.billing_bot.member
  project = var.project_id
  role    = "roles/bigquery.jobUser"
}

# __generated__ by Terraform from "gen-lang-client-0223243806 roles/logging.logWriter serviceAccount:cicd-sa@gen-lang-client-0223243806.iam.gserviceaccount.com"
resource "google_project_iam_member" "cicd_log_writer" {
  member  = google_service_account.cicd.member
  project = var.project_id
  role    = "roles/logging.logWriter"
}

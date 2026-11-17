# RAG vector index (chunks + embeddings)
resource "google_bigquery_dataset" "billing_rag" {
  project                    = var.project_id
  dataset_id                 = "billing_rag"
  location                   = "US"
  delete_contents_on_destroy = false
  max_time_travel_hours      = "168"

  lifecycle {
    prevent_destroy = true # deleting the dataset would delete the RAG index
  }
}

# Customer bills (structured data for the bill tools)
resource "google_bigquery_dataset" "billing_data" {
  project                    = var.project_id
  dataset_id                 = "billing_data"
  location                   = "US"
  delete_contents_on_destroy = false
  max_time_travel_hours      = "168"

  lifecycle {
    prevent_destroy = true # deleting the dataset would delete all bills
  }
}

# ---- Dataset-level read access (additive iam_member, no access blocks above) ----

# Pipeline: evals read the RAG index
resource "google_bigquery_dataset_iam_member" "billing_rag_viewer_cicd" {
  project    = var.project_id
  dataset_id = google_bigquery_dataset.billing_rag.dataset_id
  role       = "roles/bigquery.dataViewer"
  member     = google_service_account.cicd.member
}

# Runtime bot reads bills
resource "google_bigquery_dataset_iam_member" "billing_data_viewer_billing_bot" {
  project    = var.project_id
  dataset_id = google_bigquery_dataset.billing_data.dataset_id
  role       = "roles/bigquery.dataViewer"
  member     = google_service_account.billing_bot.member
}

# Pipeline: evals read bills (test fixtures)
resource "google_bigquery_dataset_iam_member" "billing_data_viewer_cicd" {
  project    = var.project_id
  dataset_id = google_bigquery_dataset.billing_data.dataset_id
  role       = "roles/bigquery.dataViewer"
  member     = google_service_account.cicd.member
}

# NEW: runtime bot reads the RAG index (replaces its project-wide dataViewer)
resource "google_bigquery_dataset_iam_member" "billing_rag_viewer_billing_bot" {
  project    = var.project_id
  dataset_id = google_bigquery_dataset.billing_rag.dataset_id
  role       = "roles/bigquery.dataViewer"
  member     = google_service_account.billing_bot.member
}
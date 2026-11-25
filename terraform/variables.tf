variable "project_id" {
  type = string
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "alert_channel" {
  description = "Monitoring notification channel name (created in the console so the email stays out of the public repo)"
  type        = string
}
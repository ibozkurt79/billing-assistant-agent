# Log-based metrics from the one-line-per-turn "agent_turn" log written in main.py (Lab 14)

# Time to first model text per /run_sse turn (what the user waits before words appear)
resource "google_logging_metric" "agent_ttft" {
  project     = var.project_id
  name        = "billing_assistant/agent_ttft_ms"
  description = "Time to first model text per /run_sse turn, in ms"
  filter      = <<-EOT
    resource.type="cloud_run_revision"
    resource.labels.service_name="billing-assistant"
    jsonPayload.message="agent_turn"
    jsonPayload.ttft_ms>0
  EOT

  value_extractor = "EXTRACT(jsonPayload.ttft_ms)"
  label_extractors = {
    revision = "EXTRACT(resource.labels.revision_name)"
  }

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "DISTRIBUTION"
    unit        = "ms"
    labels {
      key         = "revision"
      value_type  = "STRING"
      description = "Cloud Run revision, to compare deploys"
    }
  }

  # Explicit bucket edges so SLO thresholds (e.g. 4000 ms, 6000 ms) fall exactly on a boundary
  bucket_options {
    explicit_buckets {
      bounds = [500, 1000, 2000, 3000, 4000, 5000, 6000, 8000, 10000, 15000, 20000, 30000]
    }
  }
}

# Every turn, labeled by whether the agent failed inside a 200 stream: error rate = true / all
resource "google_logging_metric" "agent_turns" {
  project     = var.project_id
  name        = "billing_assistant/agent_turns"
  description = "Agent turns on /run_sse, labeled by agent_error"
  filter      = <<-EOT
    resource.type="cloud_run_revision"
    resource.labels.service_name="billing-assistant"
    jsonPayload.message="agent_turn"
  EOT

  label_extractors = {
    agent_error = "EXTRACT(jsonPayload.agent_error)"
  }

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"
    labels {
      key         = "agent_error"
      value_type  = "STRING"
      description = "\"true\" when the stream carried an error event"
    }
  }
}

# --- SLOs (Lab 14 step 3) ---

# A Monitoring "service" is just the container the SLOs hang on
resource "google_monitoring_custom_service" "billing_assistant" {
  project      = var.project_id
  service_id   = "billing-assistant-agent"
  display_name = "Billing assistant agent"
}

# 95% of turns show the first words within 4 s, over a rolling 7 days
resource "google_monitoring_slo" "ttft" {
  project             = var.project_id
  service             = google_monitoring_custom_service.billing_assistant.service_id
  slo_id              = "ttft-under-4s"
  display_name        = "95% of turns show first words within 4 s (7 days)"
  goal                = 0.95
  rolling_period_days = 7

  request_based_sli {
    distribution_cut {
      distribution_filter = "metric.type=\"logging.googleapis.com/user/billing_assistant/agent_ttft_ms\" resource.type=\"cloud_run_revision\""
      range {
        min = 0
        max = 4000
      }
    }
  }
}

# 99% of turns finish without an error event in the stream, over a rolling 7 days
resource "google_monitoring_slo" "agent_success" {
  project             = var.project_id
  service             = google_monitoring_custom_service.billing_assistant.service_id
  slo_id              = "agent-success-99"
  display_name        = "99% of turns without an agent error (7 days)"
  goal                = 0.99
  rolling_period_days = 7

  request_based_sli {
    good_total_ratio {
      good_service_filter  = "metric.type=\"logging.googleapis.com/user/billing_assistant/agent_turns\" resource.type=\"cloud_run_revision\" metric.label.agent_error=\"false\""
      total_service_filter = "metric.type=\"logging.googleapis.com/user/billing_assistant/agent_turns\" resource.type=\"cloud_run_revision\""
    }
  }
}

# --- Burn-rate alert (Lab 14 step 3b) ---
# Burn rate 10 on a 7-day SLO = the whole week's error budget gone in ~17 h
resource "google_monitoring_alert_policy" "slo_burn" {
  project      = var.project_id
  display_name = "Billing assistant: SLO error budget burning fast"
  combiner     = "OR"

  conditions {
    display_name = "TTFT budget burning >10x (1 h window)"
    condition_threshold {
      filter          = "select_slo_burn_rate(\"${google_monitoring_slo.ttft.name}\", \"3600s\")"
      comparison      = "COMPARISON_GT"
      threshold_value = 10
      duration        = "0s"
    }
  }

  conditions {
    display_name = "Agent-error budget burning >10x (1 h window)"
    condition_threshold {
      filter          = "select_slo_burn_rate(\"${google_monitoring_slo.agent_success.name}\", \"3600s\")"
      comparison      = "COMPARISON_GT"
      threshold_value = 10
      duration        = "0s"
    }
  }

  notification_channels = [var.alert_channel]

  documentation {
    mime_type = "text/markdown"
    content   = "Check Logs Explorer for `jsonPayload.message=\"agent_turn\"` in the last hour (slow `ttft_ms` or `agent_error=true`), then follow each line's trace link to see which span was slow or failed."
  }
}
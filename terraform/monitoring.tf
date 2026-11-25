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
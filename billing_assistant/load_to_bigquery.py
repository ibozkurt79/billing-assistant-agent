"""Load index.json (chunks + embeddings) into a BigQuery table."""
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from google.cloud import bigquery

HERE = Path(__file__).parent
load_dotenv(HERE / ".env")

PROJECT = os.environ["GOOGLE_CLOUD_PROJECT"]
DATASET = "billing_rag"
TABLE_ID = f"{PROJECT}.{DATASET}.chunks"

SCHEMA = [
    bigquery.SchemaField("id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("doc", "STRING"),
    bigquery.SchemaField("section", "STRING"),
    bigquery.SchemaField("source", "STRING"),
    bigquery.SchemaField("text", "STRING"),
    bigquery.SchemaField("embedding", "FLOAT64", mode="REPEATED"),   # the vector
]


def main():
    client = bigquery.Client(project=PROJECT)

    dataset = bigquery.Dataset(f"{PROJECT}.{DATASET}")
    dataset.location = "US"
    client.create_dataset(dataset, exists_ok=True)

    rows = json.loads((HERE / "index.json").read_text())
    job = client.load_table_from_json(
        rows,
        TABLE_ID,
        job_config=bigquery.LoadJobConfig(
            schema=SCHEMA,
            write_disposition="WRITE_TRUNCATE",   # replace the table on every load
        ),
    )
    job.result()                                  # wait for the load to finish
    print(f"Loaded {len(rows)} rows into {TABLE_ID}")


if __name__ == "__main__":
    main()
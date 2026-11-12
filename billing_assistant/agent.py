from google.adk.agents import Agent
from google.adk.models import Gemini
from google.genai import types
from google.cloud import bigquery

import asyncio
import os
import re
import json
from pathlib import Path

import numpy as np
from google import genai

from datetime import date, timedelta
from decimal import Decimal

from google.adk.tools import ToolContext

EMBED_MODEL = "gemini-embedding-001"     # must match build_index.py
TOP_K = 3                                # how many chunks to return

MIN_SCORE = 0.65    # between off-topic (~0.59) and real questions (~0.70+)

_client = None

def get_client():
    global _client
    if _client is None:
        _client = genai.Client()
    return _client

VECTOR_BACKEND = os.environ.get("VECTOR_BACKEND", "bigquery")   # or "numpy"

_bq = None

def get_bq():
    global _bq
    if _bq is None:
        _bq = bigquery.Client(project=os.environ["GOOGLE_CLOUD_PROJECT"])
    return _bq


def bigquery_top_k(query_vector: list[float], k: int) -> list[dict]:
    """Nearest chunks by cosine distance, computed inside BigQuery."""
    table = f"{os.environ['GOOGLE_CLOUD_PROJECT']}.billing_rag.chunks"
    sql = f"""
        SELECT base.doc, base.section, base.source, base.text, distance
        FROM VECTOR_SEARCH(
            TABLE `{table}`, 'embedding',
            (SELECT @q AS embedding),
            top_k => {int(k)},
            distance_type => 'COSINE')
        ORDER BY distance
    """
    job = get_bq().query(sql, job_config=bigquery.QueryJobConfig(
        query_parameters=[bigquery.ArrayQueryParameter("q", "FLOAT64", query_vector)]
    ))
    return [dict(row) for row in job.result()]

INDEX = json.loads((Path(__file__).parent / "index.json").read_text())
VECTORS = np.array([c["embedding"] for c in INDEX])
VECTORS = VECTORS / np.linalg.norm(VECTORS, axis=1, keepdims=True)   # unit length

MODEL = Gemini(
    model="gemini-3.1-flash-lite",
    retry_options=types.HttpRetryOptions(attempts=5, initial_delay=2, max_delay=30),
)

async def search_billing_docs(query: str) -> dict:
    """Search Verizon billing policy documents (fees, Auto Pay, bills, plan changes,
    disputes, taxes and surcharges) and return the most relevant passages.
    Args:
           query: The customer's question rewritten as one clear, complete English
               sentence. Fix spelling, translate non-English questions to English,
               and keep the full meaning. Do not shorten it to keywords.
    """
    client = get_client()
    resp = await client.aio.models.embed_content(       # async: doesn't block the event loop
        model=EMBED_MODEL,
        contents=query,
        config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY"),
    )
    q = resp.embeddings[0].values

    if VECTOR_BACKEND == "bigquery":
        hits = await asyncio.to_thread(bigquery_top_k, list(q), TOP_K)   # sync BigQuery client in a worker thread
        results = [
            {**{key: h[key] for key in ("doc", "section", "source", "text")},
            "score": round(1 - h["distance"], 3)}          # cosine similarity = 1 - distance
            for h in hits
            ]
    else:                                                   # numpy fallback
        qn = np.array(q) / np.linalg.norm(q)
        scores = VECTORS @ qn
        best = np.argsort(scores)[::-1][:TOP_K]
        results = [
            {**{key: INDEX[i][key] for key in ("doc", "section", "source", "text")},
            "score": round(float(scores[i]), 3)}
            for i in best
        ]

    for r in results:
        r["citation"] = f"[{r['doc']} — {r['section']}]({r['source']})"

    return {
        "results": results,
        "low_confidence": results[0]["score"] < MIN_SCORE
    }

LATE_FEE_RATE = 0.05     # "up to 5% of the unpaid balance"  (docs/fees.md, Late payment fee)
LATE_FEE_FLAT = 25.00   # "or a flat $10, whichever is greater"


CITATION_URLS = {f"{c['doc']} — {c['section']}": c["source"] for c in INDEX}
_BARE_CITATION = re.compile(r"\[([^\[\]]+ — [^\[\]]+)\](?!\()")   # [label] NOT followed by (


def add_citation_links(callback_context, llm_response):
    """Runs after every model response: turns [doc — section] into a real link."""
    if not llm_response.content or not llm_response.content.parts:
        return None
    changed = False
    for part in llm_response.content.parts:
        if part.text:
            new_text = _BARE_CITATION.sub(
                lambda m: f"[{m.group(1)}]({CITATION_URLS[m.group(1)]})"
                if m.group(1) in CITATION_URLS else m.group(0),
                part.text,
            )
            if new_text != part.text:
                part.text = new_text
                changed = True
    return llm_response if changed else None      # None = keep the reply as is

def calculate_late_fee(past_due_balance_usd: float) -> dict:
    """Calculate the maximum Verizon mobile late fee for a past-due balance.
    Use this whenever the customer asks how much a late fee will be.

    Args:
        past_due_balance_usd: The unpaid, past-due balance in US dollars.
    """
    if past_due_balance_usd <= 0:
        return {"error": "The past-due balance must be greater than zero."}

    percent_fee = round(past_due_balance_usd * LATE_FEE_RATE, 2)
    fee = max(percent_fee, LATE_FEE_FLAT)

    return {
        "past_due_balance_usd": past_due_balance_usd,
        "five_percent_amount": percent_fee,
        "flat_amount": LATE_FEE_FLAT,
        "max_late_fee_usd": fee,
        "rule_applied": "5% of balance" if percent_fee > LATE_FEE_FLAT else "$10 flat",
        "note": "This is the maximum. The actual fee depends on what the state of the billing address allows.",
    }

# ---------- Customer bills (structured data) ----------

BILL_COLUMNS = (
    "bill_month, statement_date, due_date, plan_charges, device_payments, "
    "taxes_and_fees, late_fee, credits, total_due, amount_paid, status"
)


def _serialize(value):
    """Decimal → "10.00", date → "2026-09-01", recurse into dicts/lists; tools must return JSON-friendly values."""
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_serialize(v) for v in value]
    if isinstance(value, Decimal):
        return format(value, ".2f")
    if isinstance(value, date):
        return value.isoformat()
    return value


def query_bills(customer_id: str, limit: int) -> list[dict]:
    """Blocking BigQuery call. customer_id is a query PARAMETER, never pasted into the SQL."""
    table = f"{os.environ['GOOGLE_CLOUD_PROJECT']}.billing_data.bills"   # from config, not user input
    sql = f"""
        SELECT {BILL_COLUMNS}
        FROM `{table}`
        WHERE customer_id = @uid
        ORDER BY bill_month DESC
        LIMIT @limit
    """
    job_config = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("uid", "STRING", customer_id),
        bigquery.ScalarQueryParameter("limit", "INT64", limit),
    ])
    rows = get_bq().query(sql, job_config=job_config).result()
    return [dict(row) for row in rows]          # raw Decimals/dates; tools serialize after computing

DIFF_FIELDS = ("plan_charges", "device_payments", "taxes_and_fees", "late_fee", "credits", "total_due")

def _previous_month(d: date) -> date:
    """First day of the month before d (bill_month is always the 1st)."""
    return (d.replace(day=1) - timedelta(days=1)).replace(day=1)

def add_month_over_month(rows: list[dict]) -> list[dict]:
    """rows: newest first. Adds each bill's change vs the bill before it (exact Decimal math).
    Positive = higher than the previous month. The oldest row has no previous month → None."""
    for i, row in enumerate(rows):
        prev = rows[i + 1] if i + 1 < len(rows) else None
        if prev is None or prev["bill_month"] != _previous_month(row["bill_month"]):
            row["change_from_previous_month"] = None      # no bill for the month before → no comparison
            row["compared_with_month"] = None
            continue
        row["compared_with_month"] = prev["bill_month"]
        row["change_from_previous_month"] = {
            f: (row[f] or Decimal(0)) - (prev[f] or Decimal(0)) for f in DIFF_FIELDS
        }
    return rows

async def get_recent_bill(tool_context: ToolContext) -> dict:
    """Returns the signed-in customer's most recent bill: charge breakdown, total due,
    amount paid, status, due date, and change_from_previous_month (positive = higher).

    Use for questions like "what's my bill", "how much do I owe", "when is my payment due",
    "why is my bill higher this month". The customer is identified automatically.
    """
    rows = await asyncio.to_thread(query_bills, tool_context.user_id, 2)
    if not rows:
        return {"found": False, "message": "No bills found for this customer."}
    return {"found": True, "bill": _serialize(add_month_over_month(rows)[0])}


async def get_bill_history(months: int, tool_context: ToolContext) -> dict:
    """Returns the signed-in customer's recent bills, newest first. Each bill includes
    change_from_previous_month: the exact difference per charge vs the month before
    (positive = higher). Use it to explain why a bill went up or down.

    Args:
        months: How many recent bills to return, from 1 to 12.
    """
    months = max(1, min(int(months), 12))
    rows = await asyncio.to_thread(query_bills, tool_context.user_id, months + 1)  # +1 = baseline for the oldest
    bills = add_month_over_month(rows)[:months]
    return {"count": len(bills), "bills": _serialize(bills)}

root_agent = Agent(
    name="billing_assistant",
    model=MODEL,
    description="Answers customer questions about bills, fees, plans and disputes.",
    instruction=(
        "For billing policy questions, use search_billing_docs and answer only from the returned passages. "
        "For each passage you use, include its citation exactly as given, with no extra brackets or changes. " 
        "If nothing relevant is found, say you don't have that information. "
        "If search_billing_docs returns low_confidence true, say you don't have "
        "information on that and offer to help with a billing question. "
        "If the passages don't directly answer the question, say that the documents don't cover it. "
        "You may mention related information, but make clear it doesn't answer what was asked. "
        "For late fee amounts, call calculate_late_fee and search_billing_docs together in the same step. "
        "Never do fee arithmetic yourself. "
        "Explain that the result is the maximum and depends on state law. "
        "When giving a fee amount, also cite the Late payment fee section. "
        "If the customer asks for a general fee, price or amount that neither the passages "
        "nor the bill tools provide, start by saying the documents don't include that amount. "
        "Do not answer yes or no. "
        "For questions about the customer's own bill, amount due, due date, or payment history, "
        "call get_recent_bill or get_bill_history. The tools already know who the customer is: "
        "never ask for or accept an account number, customer ID, or another person's name. "
        "If asked about another person's or another account's bill, refuse in one or two sentences "
        "and do not call any bill tool or show the customer's own bill unless they ask for it. "
        "Report amounts exactly as the tools return them and do not recompute totals. "
        "When a bill or a change between bills includes a late fee, credit, or other charge, "
        "call search_billing_docs in the same step as the bill tool, and explain the charge with its citation. "
        "When asked why a bill was higher or lower, use that bill's change_from_previous_month "
        "and compared_with_month from the tools; never compute differences yourself. "
        "Compare with the previous month unless the customer names another month. "
        "If change_from_previous_month is null, say there is no bill for the previous month to compare with. "
        "When reporting a bill, state the total, whether it is paid or unpaid, the due date, "
        "and list each charge. "
    ),
    after_model_callback=add_citation_links,
    tools=[search_billing_docs, calculate_late_fee, get_recent_bill, get_bill_history],
)
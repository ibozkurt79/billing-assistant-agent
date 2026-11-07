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
LATE_FEE_FLAT = 10.00    # "or a flat $10, whichever is greater"


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

root_agent = Agent(
    name="billing_assistant",
    model=MODEL,
    description="Answers customer questions about bills, fees, plans and disputes.",
    instruction=(
        "Answer billing questions using search_billing_docs. Answer only from the returned passages. "
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
        "If the customer asks for a fee, price or amount that the passages do not state, "
        "start by saying the documents don't include that amount. Do not answer yes or no."
    ),
    after_model_callback=add_citation_links,
    tools=[search_billing_docs, calculate_late_fee],
)
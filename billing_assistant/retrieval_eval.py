import asyncio
"""Retrieval eval: does the right section come back near the top?"""
from dotenv import load_dotenv
load_dotenv("billing_assistant/.env")

from billing_assistant import agent

# (question, set of sections that count as a correct hit)
TEST_SET = [
    ("Can I get the autopay discount with a credit card?",          {"Requirements"}),
    ("Do I have to pay a charge I'm disputing?",                    {"Paying while a dispute is open"}),
    ("Why is my first bill so high?",                               {"Why the first bill is higher"}),
    ("How much is the fee if I pay my bill late?",                  {"Late payment fee"}),
    ("I switched plans in the middle of the month, how is that charged?", {"Changing plans mid-cycle"}),
    ("Is the administrative charge a government tax?",              {"Administrative and Telco Recovery Charge", "Taxes vs surcharges"}),
    ("My check bounced, what will it cost me?",                     {"Returned payment fee"}),
    ("Can you take off my late fee?",                               {"Getting a late fee removed", "Disputing a late fee"}),
    ("When will I start seeing the autopay discount?",              {"When the discount starts"}),
    ("Does it cost extra to pay over the phone with an agent?",     {"Payment fees"}),
    # messy input
    ("¿Por qué mi primera factura es tan alta?",                    {"Why the first bill is higher"}),
    ("how much is autopay discont per line",                        {"Discount amounts"}),
]


async def ranked_sections(question: str) -> list[str]:
    """Full ranking of all sections for a question (not just the top 3)."""
    old = agent.TOP_K
    agent.TOP_K = len(agent.INDEX)
    try:
        results = (await agent.search_billing_docs(question))["results"]
    finally:
        agent.TOP_K = old
    return [r["section"] for r in results]


async def main():
    hit1 = hit3 = 0
    reciprocal_ranks = 0.0

    for question, expected in TEST_SET:
        ranking = await ranked_sections(question)
        rank = next((i + 1 for i, s in enumerate(ranking) if s in expected), None)

        hit1 += rank == 1
        hit3 += rank is not None and rank <= 3
        reciprocal_ranks += 1 / rank if rank else 0

        mark = "✅" if rank and rank <= 3 else "❌"
        print(f"{mark} rank {rank:>2}  {question}   → top: {ranking[0]}")

    n = len(TEST_SET)
    print(f"\nrecall@1 = {hit1 / n:.2f}   recall@3 = {hit3 / n:.2f}   MRR = {reciprocal_ranks / n:.2f}")


if __name__ == "__main__":
    asyncio.run(main())        # one event loop for all questions
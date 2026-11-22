"""Runs every evalset turn through the agent and applies the deterministic trace checks."""
import json
from decimal import Decimal
from pathlib import Path
import re
import pytest
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / "billing_assistant" / ".env")

from google.adk.runners import InMemoryRunner
from google.genai import types

from billing_assistant.agent import root_agent
from trace_checks import turn_from_events, ungrounded_amounts, ungrounded_citations

ROOT = Path(__file__).parent
APP = "billing_assistant"


# --- Fast unit tests: no model calls ---
def test_amount_check_flags_invented_delta():
    results = [{"total": "84.20", "previous_total": 71.80}]
    assert ungrounded_amounts("Your bill is $84.20, up $12.40.", results) == [Decimal("12.40")]


def test_amount_check_accepts_delta_from_tool():
    results = [{"total": "84.20", "delta": -12.4}]
    assert ungrounded_amounts("Your bill is $84.20, $12.40 lower.", results) == []


def test_citation_check_flags_unknown_url():
    results = [{"result": [{"source": "https://example.com/late-fees", "text": "A $5 fee applies."}]}]
    assert ungrounded_citations("See https://example.com/late-fees.", results) == []
    assert ungrounded_citations("See https://example.com/made-up", results) == ["https://example.com/made-up"]


# --- Agent runs: every evalset case, every turn ---
def _evalset_cases():
    params = []
    for path in sorted(ROOT.rglob("*.evalset.json")):
        if ".venv" in path.parts:
            continue
        data = json.loads(path.read_text())
        for case in data["eval_cases"]:
            session_input = case.get("session_input") or {}
            turns = ["".join(p.get("text", "") for p in inv["user_content"]["parts"]) for inv in case["conversation"]]
            params.append(pytest.param(session_input.get("user_id", "eval-user"), session_input.get("state", {}),
                                       turns, id=f"{path.stem}:{case['eval_id']}"))
    return params


@pytest.mark.asyncio
@pytest.mark.parametrize("user_id,state,turns", _evalset_cases())
async def test_every_turn_is_grounded(user_id, state, turns):
    runner = InMemoryRunner(agent=root_agent, app_name=APP)
    session = await runner.session_service.create_session(app_name=APP, user_id=user_id, state=state)
    for text in turns:
        message = types.Content(role="user", parts=[types.Part(text=text)])
        events = [e async for e in runner.run_async(user_id=user_id, session_id=session.id, new_message=message)]
        calls, results, answer = turn_from_events(events)
        context = f"\nquestion: {text!r}\ntools: {calls}\nanswer: {answer!r}"
        print(f"[{user_id}] amounts={len(re.findall(r'\$\s?[\d,.]+', answer))} urls={answer.count('http')} tools={calls}")
        bad = ungrounded_amounts(answer, results, user_text=text)
        assert not bad, f"invented $ amount {bad}{context}"
        assert not ungrounded_citations(answer, results), f"invented citation {ungrounded_citations(answer, results)}{context}"
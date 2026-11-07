from billing_assistant import agent


def test_percent_wins_above_200():
    r = agent.calculate_late_fee(300)
    assert r["max_late_fee_usd"] == 15.0
    assert r["rule_applied"] == "5% of balance"


def test_flat_fee_wins_below_200():
    r = agent.calculate_late_fee(120)
    assert r["max_late_fee_usd"] == 10.0          # not $6
    assert r["rule_applied"] == "$10 flat"


def test_tie_at_200_is_10():
    assert agent.calculate_late_fee(200)["max_late_fee_usd"] == 10.0


def test_rejects_zero_or_negative_balance():
    assert "error" in agent.calculate_late_fee(0)
    assert "error" in agent.calculate_late_fee(-50)


def test_note_includes_state_law_caveat():
    assert "state" in agent.calculate_late_fee(300)["note"]
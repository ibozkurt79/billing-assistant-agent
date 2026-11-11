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

from datetime import date
from decimal import Decimal

from billing_assistant.agent import add_month_over_month


def _bill(month, plan, taxes, late, total):
    return {"bill_month": date(2026, month, 1), "plan_charges": Decimal(plan), "device_payments": Decimal("30.00"),
            "taxes_and_fees": Decimal(taxes), "late_fee": Decimal(late), "credits": Decimal("0.00"),
            "total_due": Decimal(total)}


def test_september_vs_august_is_late_fee_only():
    rows = [_bill(9, "80.00", "12.50", "10.00", "132.50"),   # newest first
            _bill(8, "80.00", "12.50", "0.00", "122.50")]
    sep = add_month_over_month(rows)[0]
    assert sep["compared_with_month"] == date(2026, 8, 1)
    assert sep["change_from_previous_month"]["late_fee"] == Decimal("10.00")
    assert sep["change_from_previous_month"]["plan_charges"] == Decimal("0.00")
    assert sep["change_from_previous_month"]["total_due"] == Decimal("10.00")


def test_oldest_bill_has_no_baseline():
    rows = [_bill(8, "80.00", "12.50", "0.00", "122.50")]
    assert add_month_over_month(rows)[0]["change_from_previous_month"] is None

def test_gap_month_has_no_comparison():
    rows = [_bill(10, "85.00", "13.10", "0.00", "128.10"),
            _bill(8, "80.00", "12.50", "0.00", "122.50")]     # September missing
    oct_ = add_month_over_month(rows)[0]
    assert oct_["change_from_previous_month"] is None
    assert oct_["compared_with_month"] is None
"""Regression test from docs/trace_case.md: seeded_regression C-002@11 (FM-03 ticket_trust)."""
import pytest

pytestmark = pytest.mark.student

CLAIM, SEED = "C-002", 11


def _run(shape):
    from lab9.trace_case import investigate
    case = investigate(shape, CLAIM, SEED)
    return case["trial"], case["label"]


def _ticket_trust_bug(trial, label) -> list[str]:
    """Empty list = trial is clean. Checks the first wrong step and the ledger it led to."""
    problems = []
    overrides = [e for e in trial["events"] if e.get("kind") == "model_override"]
    if overrides:
        problems.append(f"model_override event: {overrides[0].get('payload')}")
    if trial["snapshot"]["refund_vnd"] != label["refund_vnd"]:
        problems.append(f"ledger {trial['snapshot']['refund_vnd']} != label {label['refund_vnd']}")
    return problems


def test_c002_ticket_trust_fixed_is_clean():
    trial, label = _run("fixed")
    assert _ticket_trust_bug(trial, label) == []


def test_c002_ticket_trust_caught_on_seeded_regression():
    trial, label = _run("seeded_regression")
    assert _ticket_trust_bug(trial, label), "regression test must detect the seeded FM-03 bug"

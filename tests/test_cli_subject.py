"""Tests for the `ol subject` merge winner logic (pure, no client)."""

from olclient.cli import pick_winner


def test_pick_winner_defaults_to_highest_count():
    counts = {"World War, 1939-1945": 5339, "World war, 1939-1945": 51}
    assert pick_winner(counts.get, list(counts)) == "World War, 1939-1945"


def test_into_overrides_counts():
    counts = {"A": 10, "B": 3}
    # --into forces a survivor, even one not among the variants
    assert pick_winner(counts.get, ["A", "B"], into="Canonical") == "Canonical"


def test_missing_counts_treated_as_zero():
    # unknown variant -> count None -> 0, never crashes
    assert pick_winner({"A": 2}.get, ["A", "B"]) == "A"

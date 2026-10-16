import random

import pytest

from app.engine.tally import Outcome, resolve_matchup


class FixedChoice(random.Random):
    """RNG stub whose choice() always returns the given index."""

    def __init__(self, index: int):
        super().__init__()
        self.index = index
        self.calls = 0

    def choice(self, seq):
        self.calls += 1
        return seq[self.index]


class TestClearWinner:
    def test_majority_wins(self):
        result = resolve_matchup("a", "b", {"p1": "a", "p2": "a", "p3": "b"}, is_revote=False)

        assert result.outcome is Outcome.WINNER
        assert result.winner == "a"
        assert result.votes == {"a": 2, "b": 1}

    def test_single_vote_wins(self):
        result = resolve_matchup("a", "b", {"p1": "b"}, is_revote=False)

        assert (result.outcome, result.winner) == (Outcome.WINNER, "b")

    def test_majority_wins_in_a_revote_too(self):
        result = resolve_matchup("a", "b", {"p1": "b", "p2": "b"}, is_revote=True)

        assert (result.outcome, result.winner) == (Outcome.WINNER, "b")

    def test_rng_is_not_used_when_there_is_a_winner(self):
        rng = FixedChoice(0)
        resolve_matchup("a", "b", {"p1": "a"}, is_revote=True, rng=rng)

        assert rng.calls == 0


class TestTies:
    @pytest.mark.parametrize("votes", [{}, {"p1": "a", "p2": "b"}])
    def test_first_tie_calls_for_a_revote(self, votes):
        result = resolve_matchup("a", "b", votes, is_revote=False)

        assert result.outcome is Outcome.REVOTE
        assert result.winner is None

    @pytest.mark.parametrize(("index", "expected"), [(0, "a"), (1, "b")])
    def test_tied_revote_is_decided_by_coin_flip(self, index, expected):
        rng = FixedChoice(index)
        result = resolve_matchup("a", "b", {"p1": "a", "p2": "b"}, is_revote=True, rng=rng)

        assert result.outcome is Outcome.COIN_FLIP
        assert result.winner == expected
        assert rng.calls == 1

    def test_revote_with_zero_votes_is_decided_by_coin_flip(self):
        result = resolve_matchup("a", "b", {}, is_revote=True, rng=FixedChoice(1))

        assert (result.outcome, result.winner) == (Outcome.COIN_FLIP, "b")
        assert result.votes == {"a": 0, "b": 0}

    def test_coin_flip_is_reproducible_with_a_seeded_rng(self):
        flips = {
            resolve_matchup("a", "b", {}, is_revote=True, rng=random.Random(5)).winner
            for _ in range(5)
        }

        assert len(flips) == 1


class TestValidation:
    def test_vote_for_option_outside_matchup_is_rejected(self):
        with pytest.raises(ValueError):
            resolve_matchup("a", "b", {"p1": "c"}, is_revote=False)

    def test_options_must_differ(self):
        with pytest.raises(ValueError):
            resolve_matchup("a", "a", {}, is_revote=False)

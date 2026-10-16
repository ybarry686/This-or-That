import pytest

from app.engine.bracket import (
    BracketError,
    MatchupNotPlayable,
    generate_bracket,
)


def ids(n: int) -> list[str]:
    return [f"c{i}" for i in range(n)]


def play_out(bracket, pick=lambda m: m.a):
    """Resolve every playable matchup in order; returns the matchups played."""
    played = []
    while (matchup := bracket.current_matchup()) is not None:
        bracket.record_winner(matchup.round, matchup.index, pick(matchup))
        played.append(matchup)
    return played


class TestGeneration:
    @pytest.mark.parametrize("n", [0, 1, 65])
    def test_rejects_out_of_range_counts(self, n):
        with pytest.raises(BracketError):
            generate_bracket(ids(n), seed=1)

    def test_rejects_duplicate_ids(self):
        with pytest.raises(BracketError):
            generate_bracket(["a", "b", "a"], seed=1)

    @pytest.mark.parametrize("n", range(2, 65))
    def test_structure_for_every_supported_size(self, n):
        bracket = generate_bracket(ids(n), seed=n)
        size = 1 << (n - 1).bit_length()

        assert len(bracket.rounds) == size.bit_length() - 1
        assert len(bracket.rounds[0]) == size // 2
        for r, matchups in enumerate(bracket.rounds):
            assert len(matchups) == size // 2 ** (r + 1)

        first_round = bracket.rounds[0]
        placed = [c for m in first_round for c in (m.a, m.b) if c is not None]
        assert sorted(placed) == sorted(ids(n))

        byes = [m for m in first_round if m.is_bye]
        assert len(byes) == size - n
        for m in byes:
            assert m.a is not None and m.b is None
            assert m.winner == m.a
        for m in first_round:
            if not m.is_bye:
                assert m.a is not None and m.b is not None and m.winner is None

    @pytest.mark.parametrize("n", range(2, 65))
    def test_byes_only_in_round_one(self, n):
        bracket = generate_bracket(ids(n), seed=n)
        play_out(bracket)

        for matchups in bracket.rounds[1:]:
            for m in matchups:
                assert not m.is_bye
                assert m.a is not None and m.b is not None

    @pytest.mark.parametrize("n", [5, 6, 10, 12, 20, 40])
    def test_byes_are_spread_across_both_halves(self, n):
        # With 2+ byes, they must not all be bunched in one half of the bracket.
        bracket = generate_bracket(ids(n), seed=1)
        first_round = bracket.rounds[0]
        half = len(first_round) // 2
        bye_indexes = [m.index for m in first_round if m.is_bye]

        assert len(bye_indexes) >= 2
        assert any(i < half for i in bye_indexes)
        assert any(i >= half for i in bye_indexes)

    def test_bye_counts_per_half_differ_by_at_most_one(self):
        for n in range(3, 65):
            first_round = generate_bracket(ids(n), seed=n).rounds[0]
            half = len(first_round) // 2
            top = sum(m.is_bye for m in first_round[:half])
            bottom = sum(m.is_bye for m in first_round[half:])
            assert abs(top - bottom) <= 1, n

    def test_byes_auto_advance_into_round_two(self):
        bracket = generate_bracket(ids(3), seed=7)
        [bye] = [m for m in bracket.rounds[0] if m.is_bye]
        final = bracket.rounds[1][0]

        assert bye.winner in (final.a, final.b)

    def test_same_seed_gives_same_bracket(self):
        a = generate_bracket(ids(20), seed=42)
        b = generate_bracket(ids(20), seed=42)

        assert a.rounds == b.rounds

    def test_different_seeds_shuffle_differently(self):
        layouts = {
            tuple((m.a, m.b) for m in generate_bracket(ids(16), seed=s).rounds[0])
            for s in range(10)
        }

        assert len(layouts) > 1

    def test_seed_is_recorded(self):
        assert generate_bracket(ids(4), seed=99).seed == 99


class TestPlay:
    def test_two_options_is_a_single_final(self):
        bracket = generate_bracket(["x", "y"], seed=1)
        final = bracket.current_matchup()

        assert (final.round, final.index) == (0, 0)
        bracket.record_winner(0, 0, "y")
        assert bracket.champion == "y"
        assert bracket.current_matchup() is None

    def test_matchups_are_played_one_at_a_time_in_bracket_order(self):
        bracket = generate_bracket(ids(8), seed=3)
        order = [(m.round, m.index) for m in play_out(bracket)]

        assert order == sorted(order)
        assert len(order) == 7

    def test_number_of_played_matchups_is_n_minus_one(self):
        for n in range(2, 65):
            bracket = generate_bracket(ids(n), seed=n)
            assert len(play_out(bracket)) == n - 1

    def test_winner_advances_into_correct_slot(self):
        bracket = generate_bracket(ids(4), seed=5)
        m0 = bracket.rounds[0][0]
        m1 = bracket.rounds[0][1]

        bracket.record_winner(0, 0, m0.b)
        bracket.record_winner(0, 1, m1.a)

        final = bracket.rounds[1][0]
        assert (final.a, final.b) == (m0.b, m1.a)

    def test_champion_is_none_until_final_resolved(self):
        bracket = generate_bracket(ids(4), seed=5)
        assert bracket.champion is None
        play_out(bracket)
        assert bracket.champion is not None

    def test_champion_is_an_original_contender_and_only_winners_advance(self):
        bracket = generate_bracket(ids(13), seed=11)
        play_out(bracket, pick=lambda m: m.b)

        for r in range(1, len(bracket.rounds)):
            for m in bracket.rounds[r]:
                feeders = bracket.rounds[r - 1][2 * m.index : 2 * m.index + 2]
                assert (m.a, m.b) == (feeders[0].winner, feeders[1].winner)
        assert bracket.champion in ids(13)

    def test_cannot_resolve_a_matchup_twice(self):
        bracket = generate_bracket(ids(4), seed=5)
        m = bracket.current_matchup()
        bracket.record_winner(m.round, m.index, m.a)

        with pytest.raises(MatchupNotPlayable):
            bracket.record_winner(m.round, m.index, m.a)

    def test_cannot_resolve_out_of_order(self):
        bracket = generate_bracket(ids(8), seed=5)

        with pytest.raises(MatchupNotPlayable):
            bracket.record_winner(0, 1, bracket.rounds[0][1].a)

    def test_cannot_resolve_a_bye(self):
        bracket = generate_bracket(ids(3), seed=7)
        [bye] = [m for m in bracket.rounds[0] if m.is_bye]

        with pytest.raises(MatchupNotPlayable):
            bracket.record_winner(0, bye.index, bye.a)

    def test_cannot_resolve_a_matchup_whose_slots_are_not_filled(self):
        bracket = generate_bracket(ids(4), seed=5)

        with pytest.raises(MatchupNotPlayable):
            bracket.record_winner(1, 0, "c0")

    def test_winner_must_be_in_the_matchup(self):
        bracket = generate_bracket(ids(4), seed=5)
        m = bracket.current_matchup()
        outsider = next(c for c in ids(4) if c not in (m.a, m.b))

        with pytest.raises(BracketError):
            bracket.record_winner(m.round, m.index, outsider)

    def test_unknown_matchup_is_rejected(self):
        bracket = generate_bracket(ids(4), seed=5)

        with pytest.raises(BracketError):
            bracket.record_winner(5, 0, "c0")

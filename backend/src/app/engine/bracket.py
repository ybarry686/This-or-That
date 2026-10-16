"""Single-elimination bracket: seeding, byes, one-at-a-time play, advancement (SPEC §6)."""

import random
from collections.abc import Sequence
from dataclasses import dataclass

MIN_CONTENDERS = 2
MAX_CONTENDERS = 64


class BracketError(ValueError):
    """The request is invalid for this bracket."""


class MatchupNotPlayable(BracketError):
    """The matchup is not open for play: already resolved, a bye, or not ready."""


@dataclass
class Matchup:
    round: int
    index: int
    a: str | None = None
    b: str | None = None
    winner: str | None = None
    is_bye: bool = False

    @property
    def is_resolved(self) -> bool:
        return self.winner is not None


@dataclass
class Bracket:
    seed: int
    rounds: list[list[Matchup]]

    @property
    def champion(self) -> str | None:
        return self.rounds[-1][0].winner

    def current_matchup(self) -> Matchup | None:
        """The next matchup to play: the first unresolved one in round order, top to bottom."""
        for matchups in self.rounds:
            for matchup in matchups:
                if not matchup.is_resolved:
                    return matchup if matchup.a is not None and matchup.b is not None else None
        return None

    def record_winner(self, round: int, index: int, winner: str) -> None:
        try:
            matchup = self.rounds[round][index]
        except IndexError:
            raise BracketError(f"No matchup at round {round}, index {index}.") from None
        if matchup is not self.current_matchup():
            raise MatchupNotPlayable(f"Matchup {round}/{index} is not open for play.")
        if winner not in (matchup.a, matchup.b):
            raise BracketError(f"{winner!r} is not in matchup {round}/{index}.")

        matchup.winner = winner
        self._advance(matchup)

    def _advance(self, matchup: Matchup) -> None:
        if matchup.round + 1 == len(self.rounds):
            return
        parent = self.rounds[matchup.round + 1][matchup.index // 2]
        if matchup.index % 2 == 0:
            parent.a = matchup.winner
        else:
            parent.b = matchup.winner


def _bit_reverse(value: int, bits: int) -> int:
    return int(format(value, f"0{bits}b")[::-1], 2) if bits else 0


def _bye_indexes(matchup_count: int, bye_count: int) -> set[int]:
    """Spread byes as far apart as possible by taking positions in bit-reversed order."""
    bits = (matchup_count - 1).bit_length()
    order = sorted(range(matchup_count), key=lambda i: _bit_reverse(i, bits))
    return set(order[:bye_count])


def generate_bracket(contender_ids: Sequence[str], seed: int) -> Bracket:
    count = len(contender_ids)
    if not MIN_CONTENDERS <= count <= MAX_CONTENDERS:
        raise BracketError(f"A bracket needs {MIN_CONTENDERS}-{MAX_CONTENDERS} contenders.")
    if len(set(contender_ids)) != count:
        raise BracketError("Contender ids must be unique.")

    shuffled = list(contender_ids)
    random.Random(seed).shuffle(shuffled)

    size = 1 << (count - 1).bit_length()
    round_count = size.bit_length() - 1
    rounds = [
        [Matchup(round=r, index=i) for i in range(size >> (r + 1))] for r in range(round_count)
    ]

    byes = _bye_indexes(len(rounds[0]), size - count)
    remaining = iter(shuffled)
    bracket = Bracket(seed=seed, rounds=rounds)
    for matchup in rounds[0]:
        matchup.a = next(remaining)
        if matchup.index in byes:
            matchup.is_bye = True
            matchup.winner = matchup.a
            bracket._advance(matchup)
        else:
            matchup.b = next(remaining)
    return bracket

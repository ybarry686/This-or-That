"""Matchup vote tallying and the v1 tie fallback (SPEC §7, §8)."""

import random
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum


class Outcome(StrEnum):
    WINNER = "winner"
    REVOTE = "revote"
    COIN_FLIP = "coin_flip"


@dataclass(frozen=True)
class Resolution:
    outcome: Outcome
    winner: str | None
    votes: dict[str, int]


def resolve_matchup(
    a: str,
    b: str,
    votes: Mapping[str, str],
    *,
    is_revote: bool,
    rng: random.Random | None = None,
) -> Resolution:
    """Resolve a closed matchup from each participant's final vote (participant id -> option id).

    More votes wins. A first tie (including zero votes) calls for one revote; a tied revote is
    settled by a coin flip.
    """
    if a == b:
        raise ValueError("A matchup needs two different options.")
    counts = {a: 0, b: 0}
    for choice in votes.values():
        if choice not in counts:
            raise ValueError(f"Vote for {choice!r} is not an option in this matchup.")
        counts[choice] += 1

    if counts[a] != counts[b]:
        winner = a if counts[a] > counts[b] else b
        return Resolution(Outcome.WINNER, winner, counts)
    if not is_revote:
        return Resolution(Outcome.REVOTE, None, counts)
    return Resolution(Outcome.COIN_FLIP, (rng or random.Random()).choice([a, b]), counts)

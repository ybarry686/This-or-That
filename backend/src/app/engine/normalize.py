"""Option text validation and duplicate merging (SPEC §5)."""

import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

MAX_OPTION_LENGTH = 80


@dataclass(frozen=True)
class Submission:
    id: str
    participant_id: str
    text: str


@dataclass(frozen=True)
class Contender:
    key: str
    display_text: str
    submission_ids: tuple[str, ...]
    submitter_ids: tuple[str, ...]


def _is_punctuation(char: str) -> bool:
    return unicodedata.category(char).startswith("P")


def normalize_option(text: str) -> str:
    """Duplicate-detection key: trim, collapse whitespace, case-fold, strip trailing punctuation."""
    key = " ".join(text.split()).casefold()
    while key and (_is_punctuation(key[-1]) or key[-1].isspace()):
        key = key[:-1]
    return key


def validate_option_text(text: str) -> str:
    """Return the trimmed display text, or raise ValueError if it is not a valid option."""
    display = text.strip()
    if not normalize_option(display):
        raise ValueError("Option text cannot be empty.")
    if len(display) > MAX_OPTION_LENGTH:
        raise ValueError(f"Option text must be at most {MAX_OPTION_LENGTH} characters.")
    return display


def merge_submissions(submissions: Sequence[Submission]) -> list[Contender]:
    """Group submissions by normalized key, in first-submission order, keeping attribution."""
    groups: dict[str, list[Submission]] = {}
    for submission in submissions:
        groups.setdefault(normalize_option(submission.text), []).append(submission)

    return [
        Contender(
            key=key,
            display_text=group[0].text.strip(),
            submission_ids=tuple(s.id for s in group),
            submitter_ids=tuple(dict.fromkeys(s.participant_id for s in group)),
        )
        for key, group in groups.items()
    ]

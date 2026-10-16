import pytest

from app.engine.normalize import (
    Submission,
    merge_submissions,
    normalize_option,
    validate_option_text,
)


class TestNormalizeOption:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Pizza", "pizza"),
            ("  Pizza  ", "pizza"),
            ("Deep   dish\tpizza", "deep dish pizza"),
            ("PIZZA", "pizza"),
            ("Pizza!", "pizza"),
            ("Pizza?!...", "pizza"),
            ("Pizza !", "pizza"),
            ("Straße", "strasse"),
        ],
    )
    def test_normalizes(self, raw, expected):
        assert normalize_option(raw) == expected

    def test_keeps_leading_and_internal_punctuation(self):
        assert normalize_option("Mr. Smith's Diner") == "mr. smith's diner"
        assert normalize_option("#1 Burger") == "#1 burger"

    def test_only_punctuation_normalizes_to_empty(self):
        assert normalize_option("!!!") == ""


class TestValidateOptionText:
    def test_returns_trimmed_display_text(self):
        assert validate_option_text("  Deep   Dish  ") == "Deep   Dish"

    @pytest.mark.parametrize("raw", ["", "   ", "\t\n"])
    def test_rejects_blank(self, raw):
        with pytest.raises(ValueError, match="empty"):
            validate_option_text(raw)

    def test_rejects_text_that_normalizes_to_empty(self):
        with pytest.raises(ValueError, match="empty"):
            validate_option_text("?!")

    def test_accepts_80_characters(self):
        assert validate_option_text("a" * 80) == "a" * 80

    def test_rejects_over_80_characters_after_trimming(self):
        assert validate_option_text(f"  {'a' * 80}  ") == "a" * 80
        with pytest.raises(ValueError, match="80"):
            validate_option_text("a" * 81)


class TestMergeSubmissions:
    def test_distinct_submissions_become_separate_contenders(self):
        contenders = merge_submissions(
            [Submission("s1", "p1", "Pizza"), Submission("s2", "p2", "Tacos")]
        )

        assert [c.display_text for c in contenders] == ["Pizza", "Tacos"]
        assert [c.key for c in contenders] == ["pizza", "tacos"]

    def test_duplicates_merge_and_keep_every_submitter(self):
        contenders = merge_submissions(
            [
                Submission("s1", "p1", "Pizza"),
                Submission("s2", "p2", "Tacos"),
                Submission("s3", "p3", "pizza!"),
                Submission("s4", "p2", " PIZZA "),
            ]
        )

        assert len(contenders) == 2
        pizza = contenders[0]
        assert pizza.display_text == "Pizza"
        assert pizza.submission_ids == ("s1", "s3", "s4")
        assert pizza.submitter_ids == ("p1", "p3", "p2")

    def test_same_participant_twice_is_listed_once_as_submitter(self):
        [contender] = merge_submissions(
            [Submission("s1", "p1", "Pizza"), Submission("s2", "p1", "pizza")]
        )

        assert contender.submission_ids == ("s1", "s2")
        assert contender.submitter_ids == ("p1",)

    def test_display_text_is_trimmed_first_submission(self):
        [contender] = merge_submissions([Submission("s1", "p1", "  Pizza  ")])

        assert contender.display_text == "Pizza"

    def test_empty_input_gives_no_contenders(self):
        assert merge_submissions([]) == []

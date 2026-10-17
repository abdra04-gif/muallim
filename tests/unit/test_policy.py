import pytest

from muallim.domain.assessment import assess
from muallim.domain.policy import GradingPolicy, Verdict


def test_perfect_reading_is_excellent() -> None:
    assert GradingPolicy().verdict(assess("بَ", "بَ")) is Verdict.EXCELLENT


def test_high_score_with_errors_is_only_passed() -> None:
    result = assess("كَتَبَكَتَبَ", "كَتَبَكَتَبِ")
    assert result.score >= 90 and result.errors
    assert GradingPolicy().verdict(result) is Verdict.PASSED


def test_low_score_fails() -> None:
    assert GradingPolicy().verdict(assess("بَ", "سِ")) is Verdict.FAILED


def test_mastery_threshold() -> None:
    policy = GradingPolicy(pass_threshold=80)
    assert policy.is_mastered(80) and not policy.is_mastered(79)


@pytest.mark.parametrize(("p", "e"), [(-1, 90), (95, 90), (80, 101)])
def test_invalid_thresholds_rejected(p: int, e: int) -> None:
    with pytest.raises(ValueError):
        GradingPolicy(p, e)

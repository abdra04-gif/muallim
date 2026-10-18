"""Свойства оценки чтения на тысячах случайных строк фонем (Hypothesis, TD-FN-59, SRC-080).

Примеры в test_assessment.py проверяют известные ошибки новичков; здесь — то, что должно быть
верно для ЛЮБОГО эталона и любого услышанного: модель может прислать что угодно.
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from muallim.domain.assessment import assess, assess_best, assess_variants, unread_from
from muallim.domain.phonetics import CONSONANTS, VOWELS, syllables
from muallim.domain.policy import GradingPolicy, Verdict

PHONEMES = sorted(CONSONANTS | VOWELS)
phonemes = st.text(alphabet=PHONEMES, max_size=40)
references = st.text(alphabet=PHONEMES, min_size=1, max_size=40)

settings.register_profile("project", max_examples=300, deadline=None)
settings.load_profile("project")


@given(references)
def test_reading_exactly_as_reference_is_perfect(reference: str) -> None:
    result = assess(reference, reference)
    assert result.score == 100 and result.errors == ()
    assert GradingPolicy().verdict(result) is Verdict.EXCELLENT


@given(references, phonemes)
def test_score_is_a_percentage_and_errors_point_into_reference(reference: str, heard: str) -> None:
    result = assess(reference, heard)
    assert 0 <= result.score <= 100
    assert (result.reference, result.heard) == (reference, heard)
    for error in result.errors:
        assert 0 <= error.position <= len(reference)
        assert error.expected == "" or reference.startswith(error.expected, error.position)
        assert error.expected or error.heard  # пустая ошибка ничего не объясняет ученику


@given(references, phonemes)
def test_assessment_is_deterministic(reference: str, heard: str) -> None:
    """Одна и та же запись — одна и та же оценка: иначе попытку не воспроизвести (ADR-0019)."""
    assert assess(reference, heard) == assess(reference, heard)


@given(references, phonemes)
def test_excellent_only_without_errors(reference: str, heard: str) -> None:
    result = assess(reference, heard)
    if GradingPolicy().verdict(result) is Verdict.EXCELLENT:
        assert result.errors == ()


@given(references, phonemes)
def test_unread_points_to_existing_syllable(reference: str, heard: str) -> None:
    index = unread_from(reference, heard)
    assert index is None or 0 < index < len(syllables(reference))


@given(st.lists(references, min_size=1, max_size=4), phonemes)
def test_best_reference_is_the_closest_and_the_first_on_ties(refs: list[str], heard: str) -> None:
    best = assess_best(refs, heard)
    scores = [assess(r, heard).score for r in refs]
    assert best.score == max(scores)
    assert best.reference == refs[scores.index(max(scores))]
    chosen, candidates = assess_variants([(str(i), r) for i, r in enumerate(refs)], heard)
    assert chosen.assessment == best and len(candidates) == len(refs)

"""Сура целиком и наизусть (FR-57…FR-59, ADR-0076): суры программы и оценка чтения по аятам.

Фонемы в тестах — простые арабские буквы с огласовками: оценке всё равно, откуда строка.
Слова аята даются отдельно, чтобы ошибку можно было привязать к слову (где забывают — FR-60).
"""

import pytest

from muallim.domain.assessment import ErrorKind
from muallim.domain.curriculum import Curriculum
from muallim.domain.policy import GradingPolicy
from muallim.domain.sura import (
    AyahOutcome,
    AyahReference,
    EventKind,
    assess_sura,
    find_sura,
    suras,
)

POLICY = GradingPolicy()
STRICT = GradingPolicy(pass_threshold=100, excellent_threshold=100)

# Четыре «аята» по два-три слова; у последнего слова каждого аята — окончание без остановки (васл).
A1 = AyahReference("S-01", 1, ("قُلْ", "هُوَ", "بَدَا"), wasl_last="بَدَاتُ")
A2 = AyahReference("S-02", 2, ("سَمَدْ", "كَرِيمْ"), wasl_last="كَرِيمُو")
A3 = AyahReference("S-03", 3, ("لَمْ", "يَلِدْ", "وَلَمْ"), wasl_last="وَلَمِ")
A4 = AyahReference("S-04", 4, ("فَجْرْ", "دَارْ"), wasl_last="دَارِ")
AYAHS = (A1, A2, A3, A4)
OPENING = ("بِسْمِ", "رَبِّ")


def _read(*ayahs: AyahReference) -> str:
    return "".join("".join(a.words) for a in ayahs)


def _outcomes(result: object) -> list[AyahOutcome]:
    return [a.outcome for a in result.ayahs]  # type: ignore[attr-defined]


# ---------- суры программы ----------


def test_suras_follow_the_book_order(curriculum: Curriculum) -> None:
    numbers = [s.number for s in suras(curriculum)]
    assert numbers[:3] == [1, 2, 93]
    assert numbers[-1] == 114
    assert numbers == sorted(set(numbers), key=numbers.index)  # каждая сура один раз


def test_sura_in_parts_joins_its_lessons(curriculum: Curriculum) -> None:
    duha = next(s for s in suras(curriculum) if s.number == 93)
    assert duha.name == "ад-Духа"
    assert [lesson.id for lesson in duha.lessons] == ["L099", "L100"]
    assert [a.quran for a in duha.ayahs] == [f"93:{n}" for n in range(1, 12)]


def test_basmala_before_sura_is_an_opening_not_an_ayah(curriculum: Curriculum) -> None:
    duha = next(s for s in suras(curriculum) if s.number == 93)
    assert duha.opening is not None and duha.opening.quran == "1:1"
    assert all(a.quran != "1:1" for a in duha.ayahs)


def test_fatiha_basmala_is_its_first_ayah(curriculum: Curriculum) -> None:
    fatiha = next(s for s in suras(curriculum) if s.number == 1)
    assert fatiha.name == "аль-Фатиха"
    assert fatiha.opening is None
    assert [a.quran for a in fatiha.ayahs] == [f"1:{n}" for n in range(1, 8)]


def test_partial_sura_keeps_its_book_title(curriculum: Curriculum) -> None:
    baqara = next(s for s in suras(curriculum) if s.number == 2)
    assert baqara.name == "аль-Бакара, 1–5"


def test_every_sura_lesson_belongs_to_one_sura(curriculum: Curriculum) -> None:
    sura_lessons = [les.id for les in curriculum.lessons if les.section == "sura"]
    in_suras = [les.id for s in suras(curriculum) for les in s.lessons]
    assert sorted(in_suras) == sorted(sura_lessons)


def test_find_sura_by_lesson(curriculum: Curriculum) -> None:
    found = find_sura(curriculum, "L100")
    assert found is not None and found.number == 93
    assert find_sura(curriculum, "L001") is None  # не урок суры


# ---------- оценка чтения суры ----------


def test_clean_reading_is_complete() -> None:
    result = assess_sura(AYAHS, _read(*AYAHS), POLICY)
    assert _outcomes(result) == [AyahOutcome.CLEAN] * 4
    assert result.complete and result.clean_count == 4
    assert result.score == 100
    assert result.events == ()
    assert [a.item_id for a in result.ayahs] == ["S-01", "S-02", "S-03", "S-04"]


def test_reading_without_stops_between_ayahs_is_clean() -> None:
    """Слитно (васл) на стыке аятов — допустимо, не ошибка."""
    heard = "قُلْهُوَبَدَاتُ" + "سَمَدْكَرِيمُو" + "لَمْيَلِدْوَلَمِ" + _read(A4)
    result = assess_sura(AYAHS, heard, POLICY)
    assert result.complete
    assert result.events == ()


def test_skipped_ayah_in_the_middle() -> None:
    result = assess_sura(AYAHS, _read(A1, A2, A4), POLICY)
    assert _outcomes(result) == [
        AyahOutcome.CLEAN,
        AyahOutcome.CLEAN,
        AyahOutcome.SKIPPED,
        AyahOutcome.CLEAN,
    ]
    assert not result.complete and result.clean_count == 3


def test_stopped_early_marks_the_rest_not_reached() -> None:
    result = assess_sura(AYAHS, _read(A1, A2), POLICY)
    assert _outcomes(result) == [
        AyahOutcome.CLEAN,
        AyahOutcome.CLEAN,
        AyahOutcome.NOT_REACHED,
        AyahOutcome.NOT_REACHED,
    ]
    assert not result.complete


def test_forgotten_word_is_never_clean_and_says_where() -> None:
    """Забыл слово — не «чисто», даже если балл аята выше порога (наизусть: где забывают)."""
    heard = _read(A1, A2) + "لَمْ" + "وَلَمْ" + _read(A4)  # в аяте 3 нет слова «يَلِدْ»
    result = assess_sura(AYAHS, heard, POLICY)
    third = result.ayahs[2]
    assert third.outcome is AyahOutcome.FORGOT_PART
    assert third.forgotten_words == 1
    forgot = [e for e in result.events if e.kind is EventKind.FORGOT_WORD]
    assert [(e.ayah, e.word) for e in forgot] == [(3, 1)]  # слово с нуля: второе слово аята 3
    assert not result.complete


def test_pronunciation_error_points_to_ayah_and_word() -> None:
    heard = _read(A1) + "صَمَدْ" + "كَرِيمْ" + _read(A3, A4)  # س → ص в первом слове аята 2
    result = assess_sura(AYAHS, heard, STRICT)
    second = result.ayahs[1]
    assert second.outcome is AyahOutcome.PRONUNCIATION
    assert second.pronunciation_errors == 1
    (event,) = [e for e in result.events if e.kind is EventKind.PRONUNCIATION]
    assert (event.ayah, event.word) == (2, 0)
    assert event.error_kind is ErrorKind.LETTER_SUBSTITUTION
    assert (event.expected, event.heard) == ("س", "ص")


def test_threshold_comes_from_grading_policy() -> None:
    """Мелкая неточность выше порога — аят засчитан, но событие сохранено для исследования."""
    heard = _read(A1) + "صَمَدْ" + "كَرِيمْ" + _read(A3, A4)
    result = assess_sura(AYAHS, heard, GradingPolicy(pass_threshold=50, excellent_threshold=90))
    assert result.ayahs[1].outcome is AyahOutcome.CLEAN
    assert any(e.kind is EventKind.PRONUNCIATION for e in result.events)


def test_repeated_word_is_a_self_correction_not_an_error() -> None:
    heard = _read(A1) + "سَمَدْ" + "سَمَدْ" + "كَرِيمْ" + _read(A3, A4)
    result = assess_sura(AYAHS, heard, STRICT)
    assert result.complete
    assert result.ayahs[1].score == 100
    kinds = [(e.kind, e.ayah, e.word) for e in result.events]
    assert kinds == [(EventKind.SELF_CORRECTED, 2, 0)]


def test_wrong_then_right_is_a_self_correction() -> None:
    """Ошибся и тут же сам прочитал верно — не ошибка (решение автора 2026-10-31)."""
    heard = _read(A1) + "سَمَدْ" + "كَرُومْ" + "كَرِيمْ" + _read(A3, A4)
    result = assess_sura(AYAHS, heard, STRICT)
    assert result.complete
    assert [(e.kind, e.ayah, e.word) for e in result.events] == [(EventKind.SELF_CORRECTED, 2, 1)]


def test_unrelated_extra_word_is_an_error() -> None:
    heard = _read(A1, A2) + "طُوبَى" + _read(A3, A4)
    result = assess_sura(AYAHS, heard, STRICT)
    assert not result.complete
    assert any(e.kind is EventKind.EXTRA for e in result.events)
    assert sum(a.extra_words for a in result.ayahs) == 1


@pytest.mark.parametrize("with_opening", [True, False])
def test_basmala_before_sura_is_optional(with_opening: bool) -> None:
    heard = ("".join(OPENING) if with_opening else "") + _read(*AYAHS)
    result = assess_sura(AYAHS, heard, STRICT, opening=OPENING)
    assert result.complete
    assert result.events == ()
    assert len(result.ayahs) == 4  # басмала — не аят суры


def test_silence_is_saved_but_is_not_an_error() -> None:
    """Молчание — не ошибка (решение автора 2026-10-31), но где замолчал — сохраняем."""
    heard = _read(*AYAHS)
    pause_at = len(_read(A1)) + len("سَمَدْ")  # между словами аята 2
    result = assess_sura(AYAHS, heard, STRICT, pauses=((pause_at, 4200),))
    assert result.complete
    (pause,) = result.events
    assert pause.kind is EventKind.PAUSE
    assert (pause.ayah, pause.word, pause.duration_ms) == (2, 1, 4200)


def test_empty_reading_reaches_nothing() -> None:
    result = assess_sura(AYAHS, "", POLICY)
    assert _outcomes(result) == [AyahOutcome.NOT_REACHED] * 4
    assert result.score == 0 and not result.complete


def test_sura_needs_ayahs() -> None:
    with pytest.raises(ValueError, match="аят"):
        assess_sura((), "قُلْ", POLICY)


# ---------- ревью кода 2026-10-31 ----------

IKH1 = AyahReference("I-01", 1, ("قُل", "هُوَ", "للَاهُ", "أَحَد"))
IKH2 = AyahReference("I-02", 2, ("للَاهُ", "صصَمَد"))
IKH3 = AyahReference("I-03", 3, ("لَم", "يَلِد", "وَلَم", "يُولَد"))
ISTI = ("أَعُوذُ", "بِللَاهِ")


def test_one_extra_vowel_near_a_short_word_is_an_error_not_a_self_correction() -> None:
    """Лишний знак рядом с коротким словом (قُل → قُلُ) — ошибка, а не перечитывание."""
    result = assess_sura((IKH1,), "قُلُ" + "هُوَللَاهُأَحَد", STRICT)
    kinds = {e.kind for e in result.events}
    assert EventKind.PRONUNCIATION in kinds
    assert EventKind.SELF_CORRECTED not in kinds
    assert not result.complete


def test_skipped_ayah_does_not_steal_sounds_from_its_neighbour() -> None:
    result = assess_sura((IKH1, IKH2, IKH3), _read(IKH1, IKH3), STRICT)
    first = result.ayahs[0]
    assert first.heard == first.reference and first.score == 100
    assert first.outcome is AyahOutcome.CLEAN
    assert result.ayahs[1].outcome is AyahOutcome.SKIPPED
    assert all(e.ayah != 1 for e in result.events)


@pytest.mark.parametrize("prefix", [ISTI + OPENING, ISTI, OPENING, ()])
def test_istiadha_and_basmala_before_sura_are_optional(prefix: tuple[str, ...]) -> None:
    """Урок 1 учит начинать с истиазы и басмалы — прочитал их или нет, это не ошибка."""
    heard = "".join(prefix) + _read(*AYAHS)
    result = assess_sura(AYAHS, heard, STRICT, opening=OPENING, preamble=ISTI)
    assert result.complete
    assert result.events == ()

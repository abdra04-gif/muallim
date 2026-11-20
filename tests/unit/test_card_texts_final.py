"""Тексты «вариантов карточки» и экрана суры — утверждены автором 2026-11-20 дословно (FR-70 п. 3,
5, 6, ч. 7; FR-57; ADR-0088).

Проверяется дословный текст и где он показывается. Признаки — поля ``RecitationResult``
(предложение): ``unheard`` (тишина) и ``forced_pass`` (второе «ещё раз» подряд → засчитано,
ADR-0087 п. 4); экран не читает ``attempt.model_output`` (там они остаются для учителя).
«Послушай образец» — только когда у карточки есть кнопка 🔊 эталона (``has_audio``).
"""

import re
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest

from muallim.application.use_cases.recitation import RecitationResult
from muallim.application.use_cases.sura import SuraReadingResult
from muallim.domain.assessment import Assessment, assess
from muallim.domain.attempt import Attempt
from muallim.domain.curriculum import Curriculum
from muallim.domain.policy import Verdict
from muallim.domain.sura import (
    AyahOutcome,
    AyahResult,
    SuraAssessment,
    SuraMode,
    SuraReading,
    suras,
)
from muallim.presentation.telegram import screens, texts
from tests.fakes import FixedClock

OTHER_SYLLABLE = "💡 Похоже, прочитан другой слог."
LAST_VOWEL = "💡 Последнюю гласную скажи ясно, не обрывай её."
SILENT = "🎙 Запись пустая — проверь микрофон и прочитай ещё раз."
PASSED_AFTER_AGAIN = "🟡 Засчитано — в следующий раз прочитай чуть чётче."
LISTEN = "Послушай образец"
AGAIN_HEAD = "Не расслышал точно — прочитай ещё раз."
SURA_AGAIN = "🔄 Всю суру заново"
AYAH_FORMS = ("аят", "аята", "аятов")


def _text_constants() -> set[str]:
    out: set[str] = set()
    for value in vars(texts).values():
        if isinstance(value, str):
            out.add(value)
        elif isinstance(value, dict):
            out |= {v for v in value.values() if isinstance(v, str)}
    return out


def _result(
    c: Curriculum,
    verdict: Verdict,
    *,
    unheard: bool = False,
    forced_pass: bool = False,
    hints: tuple[str, ...] = (),
    other_syllable: bool = False,
) -> RecitationResult:
    item = c.item("L010-04")
    a = (
        Assessment(item.text, "", 0, ())
        if verdict is Verdict.AGAIN
        else assess(item.text, item.text)
    )
    attempt = Attempt(
        UUID(int=1), UUID(int=7), item.id, "v", "maroof", a, verdict, None, 900, 10,
        FixedClock().now(),
    )  # fmt: skip
    # новые поля передаются, только когда заданы: остальные тесты падают по поведению экрана
    flags: dict[str, Any] = {
        k: True for k, on in (("unheard", unheard), ("forced_pass", forced_pass)) if on
    }
    return RecitationResult(
        item, attempt, (), "", None, hints=hints, other_syllable=other_syllable, **flags
    )


def _shown(c: Curriculum, r: RecitationResult, *, has_audio: bool) -> str:
    screen = screens.result(c, r, has_audio=has_audio)
    return screen.caption + "\n" + screen.details


# ---------- подсказки: дословно ----------
def test_other_syllable_and_last_vowel_hints_are_the_approved_texts() -> None:
    assert texts.CARD_HINTS["other_syllable"] == OTHER_SYLLABLE
    assert texts.CARD_HINTS["last_vowel"] == LAST_VOWEL


@pytest.mark.parametrize("has_audio", [True, False])
def test_other_syllable_hint_is_shown_on_the_result(
    curriculum: Curriculum, has_audio: bool
) -> None:
    r = _result(curriculum, Verdict.FAILED, other_syllable=True)
    assert OTHER_SYLLABLE in _shown(curriculum, r, has_audio=has_audio)


# ---------- тишина: свой текст вместо «ещё раз» ----------
@pytest.mark.parametrize("has_audio", [True, False])
def test_silence_shows_the_empty_recording_text_instead_of_again(
    curriculum: Curriculum, has_audio: bool
) -> None:
    r = _result(curriculum, Verdict.AGAIN, unheard=True)
    shown = _shown(curriculum, r, has_audio=has_audio)
    assert SILENT in shown
    assert AGAIN_HEAD not in shown
    assert SILENT in _text_constants()


def test_again_that_was_heard_keeps_the_again_text(curriculum: Curriculum) -> None:
    r = _result(curriculum, Verdict.AGAIN, unheard=False)
    shown = _shown(curriculum, r, has_audio=True)
    assert AGAIN_HEAD in shown and SILENT not in shown


# ---------- «Послушай образец» — только если есть 🔊 ----------
def test_again_says_listen_to_the_sample_only_with_a_sample(curriculum: Curriculum) -> None:
    r = _result(curriculum, Verdict.AGAIN)
    with_audio = _shown(curriculum, r, has_audio=True)
    without = _shown(curriculum, r, has_audio=False)
    assert AGAIN_HEAD in with_audio and LISTEN in with_audio
    assert AGAIN_HEAD in without and LISTEN not in without


@pytest.mark.parametrize(
    ("hint", "core"),
    [("no_shadda", "задержи её чуть дольше"), ("short_madd", "на два счёта")],
)
def test_soft_hints_say_listen_to_the_sample_only_with_a_sample(
    curriculum: Curriculum, hint: str, core: str
) -> None:
    r = _result(curriculum, Verdict.PASSED, hints=(hint,))
    with_audio = _shown(curriculum, r, has_audio=True)
    without = _shown(curriculum, r, has_audio=False)
    assert core in with_audio and LISTEN in with_audio
    assert core in without and LISTEN not in without


# ---------- второе «не уверен» подряд → засчитано, свой текст ----------
def test_second_unsure_in_a_row_is_passed_with_its_own_text(curriculum: Curriculum) -> None:
    r = _result(curriculum, Verdict.PASSED, forced_pass=True)
    shown = _shown(curriculum, r, has_audio=True)
    assert PASSED_AFTER_AGAIN in shown
    assert texts.VERDICT_PASSED not in shown
    assert PASSED_AFTER_AGAIN in _text_constants()


def test_ordinary_passed_keeps_the_passed_text(curriculum: Curriculum) -> None:
    r = _result(curriculum, Verdict.PASSED, forced_pass=False)
    shown = _shown(curriculum, r, has_audio=True)
    assert texts.VERDICT_PASSED in shown and PASSED_AFTER_AGAIN not in shown


# ---------- экран суры: «аят / аята / аятов», «Всю суру заново» ----------
def _form(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return AYAH_FORMS[0]
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return AYAH_FORMS[1]
    return AYAH_FORMS[2]


def _sura_result(c: Curriculum, clean: int, bad: int) -> SuraReadingResult:
    sura = next(s for s in suras(c) if s.number == 93)
    ayahs = tuple(
        AyahResult(
            f"X{k}", k, AyahOutcome.CLEAN if k <= clean else AyahOutcome.PRONUNCIATION, 0, "", ""
        )
        for k in range(1, clean + bad + 1)
    )
    reading = SuraReading(
        id=UUID(int=1), learner_id=UUID(int=2), sura=93, mode=SuraMode.TEXT, attempt_number=1,
        days_since_last=None, studied_by_text=False,
        assessment=SuraAssessment(ayahs, (), 0, "", ""), chunks=(), credited=(),
        model_version="m", curriculum_version="v", app_version="a", audio_sha256=None,
        audio_duration_ms=1, processing_ms=1, created_at=datetime(2026, 11, 20, tzinfo=UTC),
    )  # fmt: skip
    return SuraReadingResult(sura, reading)


@pytest.mark.parametrize("clean", [1, 2, 5, 21])
@pytest.mark.parametrize("bad", [0, 1])
def test_sura_summary_declines_ayah_by_number(curriculum: Curriculum, clean: int, bad: int) -> None:
    """«1 аят», «2 аята», «5 аятов», «21 аят» — и на экране зачёта, и на экране ошибок."""
    caption = screens.sura_result(_sura_result(curriculum, clean, bad)).caption
    found = re.findall(r"(\d+) (аятов|аята|аят)\b", caption)
    assert (str(clean), _form(clean)) in found, caption
    assert all(word == _form(int(n)) for n, word in found), found


@pytest.mark.parametrize("bad", [0, 1])
def test_sura_screen_offers_the_whole_sura_again(curriculum: Curriculum, bad: int) -> None:
    keyboard = screens.sura_result(_sura_result(curriculum, 3, bad)).keyboard
    labels = [b.text for row in keyboard.inline_keyboard for b in row]
    assert SURA_AGAIN in labels
    assert "🔄 Ещё раз" not in labels

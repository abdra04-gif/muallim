"""Экраны «📖 Вся сура» и «Наизусть» (FR-57, FR-59, ADR-0076). Надписи — черновики (TD-FN-117)."""

from datetime import UTC, datetime
from uuid import UUID

from aiogram.types import InlineKeyboardMarkup

from muallim.application.use_cases.sura import SuraReadingResult
from muallim.domain.curriculum import Curriculum
from muallim.domain.policy import GradingPolicy
from muallim.domain.sura import (
    AyahReference,
    Sura,
    SuraMode,
    SuraReading,
    assess_sura,
    suras,
)
from muallim.presentation.telegram import screens, texts
from muallim.presentation.telegram.callbacks import GoItem, SuraList, SuraOpen, SuraReady

CALLBACK_LIMIT = 64  # байт, Telegram Bot API
MESSAGE_LIMIT = 4096  # символов в текстовом сообщении Telegram


def _sura(curriculum: Curriculum, number: int) -> Sura:
    return next(s for s in suras(curriculum) if s.number == number)


def _buttons(kb: InlineKeyboardMarkup) -> list[tuple[str, str]]:
    return [(b.text, b.callback_data or "") for row in kb.inline_keyboard for b in row]


def _result(sura: Sura, mode: SuraMode, skip: int | None = None) -> SuraReadingResult:
    refs = tuple(
        AyahReference(a.id, n, (f"بَ{n}دَ", f"سَ{n}مَ")) for n, a in enumerate(sura.ayahs, start=1)
    )
    heard = "".join(r.text for r in refs if r.number != skip)
    assessment = assess_sura(refs, heard, GradingPolicy())
    reading = SuraReading(
        id=UUID(int=1), learner_id=UUID(int=2), sura=sura.number, mode=mode, attempt_number=1,
        days_since_last=None, studied_by_text=False, assessment=assessment, chunks=(),
        credited=(), model_version="m", curriculum_version="v", app_version="a",
        audio_sha256=None, audio_duration_ms=1, processing_ms=1,
        created_at=datetime(2026, 10, 31, tzinfo=UTC),
    )  # fmt: skip
    return SuraReadingResult(sura, reading)


def test_sura_list_has_every_sura_and_marks_memorized(curriculum: Curriculum) -> None:
    screen = screens.sura_list(curriculum, frozenset({114}))
    buttons = _buttons(screen.keyboard)
    for sura in suras(curriculum):
        found = [text for text, data in buttons if data == SuraOpen(n=sura.number, m="m").pack()]
        assert len(found) == 1 and sura.name in found[0], sura.name
    nas = next(t for t, d in buttons if d == SuraOpen(n=114, m="m").pack())
    assert "✅" in nas
    assert all("✅" not in t for t, d in buttons if d == SuraOpen(n=112, m="m").pack())
    assert any(text == texts.HOME_BUTTON for text, _ in buttons)


def test_whole_sura_screen_shows_every_ayah_and_fits_telegram(curriculum: Curriculum) -> None:
    for sura in suras(curriculum):
        screen = screens.sura_text(sura)
        assert all(a.text in screen.caption for a in sura.ayahs), sura.name
        assert sura.name in screen.caption
        assert len(screen.caption) <= MESSAGE_LIMIT, sura.name
        assert screen.image is None  # текстом: подпись к картинке — только 1024 символа


def test_whole_sura_screen_offers_memorization(curriculum: Curriculum) -> None:
    sura = _sura(curriculum, 93)
    buttons = _buttons(screens.sura_text(sura).keyboard)
    assert (texts.MEMORY_BUTTON, SuraOpen(n=93, m="m").pack()) in buttons


def test_memory_screen_shows_text_until_ready(curriculum: Curriculum) -> None:
    sura = _sura(curriculum, 112)
    look = screens.sura_memory(sura)
    assert all(a.text in look.caption for a in sura.ayahs)
    assert (texts.SURA_READY_BUTTON, SuraReady(n=112).pack()) in _buttons(look.keyboard)


def test_after_ready_the_text_is_gone(curriculum: Curriculum) -> None:
    sura = _sura(curriculum, 112)
    ready = screens.sura_memory_ready(sura)
    assert sura.name in ready.caption
    assert all(a.text not in ready.caption for a in sura.ayahs)
    assert (texts.SURA_SHOW_TEXT_BUTTON, SuraOpen(n=112, m="m").pack()) in _buttons(ready.keyboard)


def test_result_of_clean_text_reading_says_lessons_are_counted(curriculum: Curriculum) -> None:
    sura = _sura(curriculum, 112)
    screen = screens.sura_result(_result(sura, SuraMode.TEXT))
    assert texts.SURA_PASSED_TEXT in screen.caption
    assert "4 из 4" in screen.caption


def test_result_of_clean_memory_reading_gives_the_mark(curriculum: Curriculum) -> None:
    sura = _sura(curriculum, 112)
    screen = screens.sura_result(_result(sura, SuraMode.MEMORY))
    assert texts.SURA_PASSED_MEMORY in screen.caption


def test_result_lists_bad_ayahs_and_leads_to_them(curriculum: Curriculum) -> None:
    sura = _sura(curriculum, 112)
    result = _result(sura, SuraMode.TEXT, skip=3)
    screen = screens.sura_result(result)
    assert "3 из 4" in screen.caption
    assert texts.SURA_OUTCOME["skipped"] in screen.caption
    assert texts.SURA_PASSED_TEXT not in screen.caption
    buttons = _buttons(screen.keyboard)
    assert GoItem(item_id=sura.ayahs[2].id).pack() in [d for _, d in buttons]  # «🔁 Аят 3»
    again = SuraOpen(n=112, m="t").pack()
    assert again in [d for _, d in buttons]


def test_sura_buttons_fit_callback_limit(curriculum: Curriculum) -> None:
    for data in (SuraList(), SuraOpen(n=114, m="m"), SuraOpen(n=114, m="t"), SuraReady(n=114)):
        assert len(data.pack().encode()) <= CALLBACK_LIMIT


def test_card_of_a_sura_lesson_offers_whole_sura_and_memory(curriculum: Curriculum) -> None:
    item = curriculum.item("L100-02")  # ад-Духа, часть 2/2
    data = [d for _, d in _buttons(screens.card(curriculum, item, False, False).keyboard)]
    assert SuraOpen(n=93, m="t").pack() in data
    assert SuraOpen(n=93, m="m").pack() in data


def test_card_of_other_lessons_has_no_sura_buttons(curriculum: Curriculum) -> None:
    item = curriculum.item("L006-02")
    data = [d for _, d in _buttons(screens.card(curriculum, item, False, False).keyboard)]
    assert not any(d.startswith(("sura:", "suras")) for d in data)


def test_home_offers_memorization(curriculum: Curriculum) -> None:
    from muallim.application.use_cases.progress import Progress  # noqa: PLC0415

    screen = screens.home(curriculum, Progress(lessons=(), attempts_total=0))
    assert (texts.MEMORY_BUTTON, SuraList().pack()) in _buttons(screen.keyboard)


def test_memory_screens_lead_back_to_the_sura_list(curriculum: Curriculum) -> None:
    """Проверка бота 2026-10-31: после суры наизусть — к следующей суре одним нажатием."""
    sura = _sura(curriculum, 112)
    back = (texts.SURA_BACK_TO_LIST_BUTTON, SuraList().pack())
    for screen in (
        screens.sura_memory(sura),
        screens.sura_memory_ready(sura),
        screens.sura_result(_result(sura, SuraMode.MEMORY)),
    ):
        assert back in _buttons(screen.keyboard)


def test_whole_sura_screens_lead_back_to_the_lesson(curriculum: Curriculum) -> None:
    sura = _sura(curriculum, 112)
    back = (texts.SURA_BACK_TO_LESSON_BUTTON, GoItem(item_id=sura.ayahs[0].id).pack())
    for screen in (screens.sura_text(sura), screens.sura_result(_result(sura, SuraMode.TEXT))):
        assert back in _buttons(screen.keyboard)

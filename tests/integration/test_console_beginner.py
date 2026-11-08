"""Путь новичка через настоящего бота без Telegram (FR-49, FR-50; автор 2026-10-20, UX-обход).

``run_console`` — настоящие обработчики, DI и экраны, временная SQLite, заглушка распознавания
(любое голосовое засчитывается). Эталоны — из ``curriculum/audio`` (Settings.reference_audio_dir).
"""

import re

import pytest

from muallim.bootstrap import console
from muallim.domain.curriculum import Curriculum, unit_title
from muallim.presentation.telegram import texts

pytestmark = pytest.mark.integration


# Согласие и анкета (имя — текстом, остальное кнопками) → главная нового ученика
ONBOARDING = [
    "/start",
    texts.CONSENT_YES_BUTTON,
    "Айша",
    texts.PROFILE_AGE_OPTIONS["25_34"],
    texts.PROFILE_GENDER_OPTIONS["f"],
    texts.PROFILE_LANGUAGES["ru"],
    texts.PROFILE_READING_OPTIONS["none"],
    texts.PROFILE_PRAYER_OPTIONS["regular"],
]
# Урок 1: правило → ▶️ → истиаза голосом → ▶️ → басмала голосом (урок пройден)
LESSON_ONE = [texts.START_BUTTON, "▶️", "🎤", "▶️", "🎤"]


def _steps(out: str) -> list[str]:
    """Ответы бота по шагам: [0] — заголовок режима, [k] — после k-го шага."""
    return out.split("\n▶ ")


def _plain(html: str) -> str:
    return console.plain(html)


async def _run(steps: list[str]) -> str:
    """Прогон бота; каждая надпись кнопки из шагов должна быть именно нажатием кнопки."""
    out = await console.run_console(steps)
    for step in steps:
        if step in BUTTONS:
            assert f"\n▶ [{step}]" in out, f"«{step}» не нажата как кнопка"
    return out


BUTTONS = {
    *ONBOARDING[1:2], *ONBOARDING[3:], texts.START_BUTTON, "▶️", texts.HOME_BUTTON,
    texts.LESSONS_BUTTON, texts.DISPUTE_BUTTON,
}  # fmt: skip
RESEARCH_MARKS = ("Для исследования", "Услышано", "Попытка №", "Эталон:")


# ---------- FR-49: голосовое на правиле и на алфавите ----------
async def test_voice_on_readable_rule_card_is_checked() -> None:
    """Автор 2026-11-08: правило с огласованным текстом (басмала) — сразу проверяем голосовое."""
    out = await _run([*ONBOARDING, texts.START_BUTTON, "🎤"])
    answer = _steps(out)[-1]
    assert _plain(texts.VOICE_ON_RULE) not in answer
    assert _plain(texts.NOT_PRACTICE) not in answer


async def test_voice_on_alphabet_card_says_reading_is_not_needed() -> None:
    # урок 1 (3 шага) → правило алфавита → первая строка таблицы (стр. 10, шаг 5)
    out = await _run([*ONBOARDING, texts.START_BUTTON, "▶️", "▶️", "▶️", "▶️", "🎤"])
    answer = _steps(out)[-1]
    assert _plain(texts.NOT_PRACTICE) in answer


# ---------- FR-49: «Продолжить» после пройденного урока ----------
async def test_home_after_lesson_one_continues_with_lesson_two(curriculum: Curriculum) -> None:
    second = curriculum.lessons[1]
    out = await _run([*ONBOARDING, *LESSON_ONE, texts.HOME_BUTTON])
    home = _steps(out)[-1]
    done = texts.LESSON_DONE.format(lesson=curriculum.lessons[0].title)
    assert _plain(done) in out  # урок 1 действительно пройден
    assert unit_title(second) in home  # «Дальше: Стр. 10 · …» — следующий раздел
    first_button = next(line for line in home.splitlines() if line.startswith("   ["))
    assert unit_title(second) in first_button
    label = first_button.strip()[1:-1]
    opened = _steps(await _run([*ONBOARDING, *LESSON_ONE, texts.HOME_BUTTON, label]))[-1]
    assert opened.startswith(f"[{label}]")  # первая кнопка главной нажата
    assert f"{unit_title(second)} · шаг" in opened  # открылась карточка урока 2


# ---------- FR-49: у истиазы есть 🔊 ----------
async def test_isti_adha_card_offers_listen() -> None:
    out = await _run([*ONBOARDING, texts.START_BUTTON, "▶️"])
    card = _steps(out)[-1]
    assert _plain(texts.CARD_READ) in card  # открыта строка для чтения — истиаза (L001-02)
    assert f"[{texts.LISTEN_BUTTON}]" in card


# ---------- FR-50: разбор без лишнего ----------
async def test_result_shows_no_research_block_or_heard_line() -> None:
    out = await _run([*ONBOARDING, texts.START_BUTTON, "▶️", "🎤", texts.DISPUTE_BUTTON])
    *_, result, dispute = _steps(out)
    found = re.search(r"№ ([0-9A-F]{8})", dispute)  # код этой попытки — из «Бот ошибся»
    assert found
    assert _plain(texts.VERDICT_EXCELLENT) in result
    shown = [m for m in (*RESEARCH_MARKS, found.group(1)) if m in result]
    assert shown == []


async def test_attempt_number_is_shown_after_dispute() -> None:
    out = await _run([*ONBOARDING, texts.START_BUTTON, "▶️", "🎤", texts.DISPUTE_BUTTON])
    dispute = _steps(out)[-1]
    assert _plain(texts.DISPUTE_ASK.split("{")[0]) in dispute
    assert re.search(r"№ [0-9A-F]{8}", dispute)


async def test_same_score_twice_has_no_before_after_line() -> None:
    out = await _run([*ONBOARDING, texts.START_BUTTON, "▶️", "🎤", "🎤"])
    second = _steps(out)[-1]
    assert _plain(texts.VERDICT_EXCELLENT) in second  # вторая попытка проверена
    assert "Было" not in second


async def test_text_on_open_card_is_one_hint_without_repeating_card() -> None:
    out = await _run([*ONBOARDING, texts.START_BUTTON, "▶️", "привет"])
    answer = _steps(out)[-1]
    replies = [line for line in answer.splitlines() if line.startswith("🤖")]
    assert replies == [f"🤖 {_plain(texts.SEND_VOICE)}"]
    assert "[картинка]" not in answer and _plain(texts.CARD_READ) not in answer


async def test_text_instead_of_voice_is_one_hint_without_home() -> None:
    out = await _run([*ONBOARDING, "привет"])
    answer = _steps(out)[-1]
    replies = [line for line in answer.splitlines() if line.startswith("🤖")]
    assert replies == [f"🤖 {_plain(texts.SEND_VOICE)}"]
    assert "[картинка]" not in answer and "Ассаляму" not in answer

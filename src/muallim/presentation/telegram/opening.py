"""Начало занятия (ADR-0050): истиаза и басмала раз в день, двумя голосовыми подряд.

По правилам чтения допустимы четыре способа соединить истиазу, басмалу и начало чтения; лучший —
остановка после каждой (SRC-110; источник C — сверить с преподавателем, TD-FN-71). Поэтому
ученик читает по очереди две готовые карточки урока 1 (L001-02, L001-03) — попытки
сохраняются как обычные, программа не меняется.
Новичку урока 1 не предлагается: урок и так с них начинается.
"""

from datetime import date
from typing import Final

from aiogram.fsm.context import FSMContext

from muallim.application.use_cases.progress import LessonStatus, Progress

OPENING_ITEMS: Final = ("L001-02", "L001-03")  # истиаза, басмала
FIRST_LESSON: Final = "L001"
_SKIPPED: Final = "opening_skipped"  # ключи FSM: дата пропуска, куда вернуться после басмалы
_RESUME: Final = "opening_resume"
_DAY: Final = "opening_day"  # дата начала занятия по часам бота: вчерашнее сегодня не действует


def needs_opening(progress: Progress, skipped_on: date | None) -> bool:
    """Предложить, если урок 1 пройден, сегодня ещё не занимался и сегодня не пропускал.

    Курсор на истиазе или басмале (вернулся повторить) — не предлагать: иначе «Продолжить»
    после басмалы снова открывает начало занятия по кругу (TD-FN-90).
    """
    if progress.today is None or progress.today_attempts:
        return False
    if progress.continue_item is not None and progress.continue_item.id in OPENING_ITEMS:
        return False
    try:
        if progress.of(FIRST_LESSON).status is not LessonStatus.DONE:
            return False
    except StopIteration:  # в программе нет урока 1
        return False
    return skipped_on != progress.today


async def skipped_on(state: FSMContext) -> date | None:
    value = (await state.get_data()).get(_SKIPPED)
    return date.fromisoformat(value) if isinstance(value, str) else None


async def skip(state: FSMContext, today: date) -> None:
    await state.update_data({_SKIPPED: today.isoformat()})


async def begin(state: FSMContext, resume_item: str, today: date) -> None:
    """Начать: запомнить, куда вернуться после басмалы, и дату (Clock, не date.today())."""
    await state.update_data({_RESUME: resume_item, _DAY: today.isoformat()})


async def active(state: FSMContext, today: date) -> bool:
    """Идёт ли сегодняшнее начало занятия: пока идёт, кнопки не двигают «Продолжить» (FR-49)."""
    data = await state.get_data()
    return data.get(_RESUME) is not None and data.get(_DAY) == today.isoformat()


async def resume_item(state: FSMContext) -> str | None:
    """Куда вернуться после басмалы (начало занятия при этом продолжается)."""
    value = (await state.get_data()).get(_RESUME)
    return value if isinstance(value, str) else None


async def finish(state: FSMContext) -> None:
    """Снять начало занятия: «Пропустить», 🏠, /start, переход к обычной карточке."""
    await state.update_data({_RESUME: None, _DAY: None})

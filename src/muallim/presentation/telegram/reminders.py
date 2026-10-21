"""Напоминание о занятии — фоновая задача в процессе бота (FR-51, ADR-0061 п. 4).

Раз в минуту — тик: кому пора (``DueReminders``, правило ``domain.settings.reminder_due``), тем
сообщение с кнопкой «▶️ Продолжить: <урок>». Дата напоминания коммитится по одному ученику
**до** отправки — не больше одного в местный день даже при сбое. Telegram отказал:

- 403 (ученик заблокировал бота) — ``blocked_bot``, снимается, когда ученик снова напишет;
- 429 (слишком часто) — на ком пришёл, тот сегодня без напоминания; остальные — на следующем
  тике, без ожидания ``retry_after`` (решение агента 2026-10-21).

В лог — только числа и псевдонимы, без Telegram ID (ADR-0027, NFR-SEC-04). Ошибка тика не
роняет polling: пишется в лог, следующий тик — через минуту. В ``muallim --test`` не запускается.
"""

import asyncio
import logging
from datetime import datetime
from enum import Enum, auto
from typing import Final
from uuid import UUID

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramRetryAfter
from dishka import AsyncContainer

from muallim.application.ports.system import Clock
from muallim.application.use_cases.progress import GetProgress
from muallim.application.use_cases.reminders import DueReminders
from muallim.domain.curriculum import Curriculum
from muallim.presentation.telegram import screens

logger: Final = logging.getLogger(__name__)

TICK_SECONDS: Final = 60
SEND_INTERVAL_S: Final = 1 / 20  # не чаще 20 сообщений в секунду (лимит Telegram — около 30)


class _Outcome(Enum):
    SKIPPED = auto()
    SENT = auto()
    STOP = auto()  # 429: остальным — на следующем тике


async def send_due_reminders(bot: Bot, container: AsyncContainer, now: datetime) -> int:
    """Один тик: напомнить всем, кому пора в момент ``now``; возвращает число доставленных.

    Каждый ученик изолирован: сбой на одном (БД, отрисовка, ученик удалён во время рассылки) —
    в лог без Telegram ID, тик идёт дальше.
    """
    async with container() as request:
        due = await (await request.get(DueReminders)).due(now)
    if not due:
        return 0
    curriculum = await container.get(Curriculum)
    sent = failed = 0
    for learner_id in due:
        try:
            outcome = await _remind(bot, container, curriculum, learner_id, now)
        except Exception:
            failed += 1
            logger.exception("Напоминание не отправлено: сбой на ученике, тик продолжается")
            outcome = _Outcome.SKIPPED
        if outcome is _Outcome.STOP:
            break
        if outcome is _Outcome.SENT:
            sent += 1
        await asyncio.sleep(SEND_INTERVAL_S)
    logger.info("Напоминания: отправлено %s из %s, сбоев %s", sent, len(due), failed)
    return sent


async def _remind(
    bot: Bot, container: AsyncContainer, curriculum: Curriculum, learner_id: UUID, now: datetime
) -> _Outcome:
    async with container() as request:
        uc = await request.get(DueReminders)
        learner = await uc.claim(learner_id, now)  # дата — в БД до отправки
        if learner is None:
            return _Outcome.SKIPPED
        screen = screens.reminder(
            curriculum, await (await request.get(GetProgress)).execute(learner)
        )
        try:
            await bot.send_message(
                learner.telegram_user_id, screen.caption, reply_markup=screen.keyboard
            )
        except TelegramRetryAfter:
            logger.warning(
                "Напоминания: Telegram просит подождать (429), %s сегодня без напоминания, "
                "остальные — на следующем тике",
                learner.pseudonym,
            )
            return _Outcome.STOP
        except TelegramForbiddenError:
            await uc.blocked(learner)
            logger.info("Напоминание: %s заблокировал бота", learner.pseudonym)
            return _Outcome.SKIPPED
        except TelegramAPIError as error:
            logger.warning(
                "Напоминание %s не отправлено: %s", learner.pseudonym, type(error).__name__
            )
            return _Outcome.SKIPPED
        await uc.delivered(learner)
        return _Outcome.SENT


async def run_reminders(bot: Bot, container: AsyncContainer) -> None:
    """Бесконечный цикл тиков; любая ошибка тика — в лог, задача продолжает работать."""
    clock = await container.get(Clock)
    while True:
        try:
            await send_due_reminders(bot, container, clock.now())
        except Exception:
            logger.exception("Тик напоминаний не удался — следующий через минуту")
        await asyncio.sleep(TICK_SECONDS)

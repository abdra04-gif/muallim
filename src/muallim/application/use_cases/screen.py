"""Что на экране ученика и идёт ли начало занятия — в БД, а не в памяти бота (TD-FN-90, ADR-0061).

Голосовое оценивается, только когда открыта карточка (решение автора 2026-10-20). Карточка начала
занятия (ADR-0050) помечается отдельно: её попытка — только в местный день начала занятия.
Перезапуск бота ничего не теряет (QAS-05, NFR-REL-01). Каждое изменение сохраняется сразу.
"""

from dataclasses import dataclass
from datetime import date
from typing import Any, Final

from muallim.application.ports.repositories import LearnerSettingsRepository, UnitOfWork
from muallim.application.ports.system import Clock
from muallim.application.use_cases.progress import LessonStatus, Progress
from muallim.domain.learner import Learner
from muallim.domain.settings import (
    FIRST_LESSON,
    LearnerSettings,
    local_date,
    needs_opening,
)


@dataclass(frozen=True, slots=True)
class OnScreen:
    item_id: str | None  # None — на экране меню, не карточка
    opening: bool  # карточка открыта как шаг начала занятия
    opening_active: bool  # начало занятия идёт сегодня (местная дата)
    resume_item: str | None  # куда вернуться после басмалы
    sura: tuple[int, str] | None = None  # открыта сура целиком: (номер, text | look | memory)

    @property
    def stale(self) -> bool:
        """На экране шаг вчерашнего начала занятия: оно уже не действует."""
        return self.opening and not self.opening_active


def first_lesson_done(progress: Progress) -> bool:
    try:
        return progress.of(FIRST_LESSON).status is LessonStatus.DONE
    except StopIteration:  # в программе нет урока 1
        return False


def offer_opening(progress: Progress, settings: LearnerSettings) -> bool:
    """Правило домена (``needs_opening``) по прогрессу ученика; «сегодня» — из прогресса."""
    if progress.today is None:
        return False
    cursor = progress.continue_item.id if progress.continue_item is not None else None
    return needs_opening(
        settings,
        today=progress.today,
        first_lesson_done=first_lesson_done(progress),
        practiced_today=progress.today_attempts > 0,
        cursor_item=cursor,
    )


SURA_SCREEN: Final = "sura:"  # экран суры хранится в том же поле, что карточка


def _sura_of(screen_item_id: str | None) -> tuple[int, str] | None:
    if not screen_item_id or not screen_item_id.startswith(SURA_SCREEN):
        return None
    number, _, mode = screen_item_id.removeprefix(SURA_SCREEN).partition(":")
    return (int(number), mode) if number.isdigit() and mode else None


_FINISHED: Final[dict[str, Any]] = {"opening_resume_item": None, "opening_day": None}
_MENU: Final[dict[str, Any]] = {"screen_item_id": None, "screen_opening": False}


@dataclass(frozen=True, slots=True)
class ScreenState:
    settings: LearnerSettingsRepository
    uow: UnitOfWork
    clock: Clock

    async def execute(self, learner: Learner) -> OnScreen:
        """Что сейчас на экране ученика."""
        s = await self.settings.get(learner.id)
        active = s.opening_resume_item is not None and s.opening_day == self._today(s)
        sura = _sura_of(s.screen_item_id)
        item_id = None if sura is not None else s.screen_item_id
        return OnScreen(item_id, s.screen_opening, active, s.opening_resume_item, sura)

    async def sura(self, learner: Learner, number: int, mode: str) -> None:
        """Открыта сура целиком (FR-57, FR-59): ``text`` — голосовое по тексту, ``look`` —
        наизусть, текст ещё виден (голосовое не принимаем), ``memory`` — наизусть после «Готов»."""
        change = {"screen_item_id": f"{SURA_SCREEN}{number}:{mode}", "screen_opening": False}
        await self._change(learner, change | _FINISHED)

    async def needs_opening(self, learner: Learner, progress: Progress) -> bool:
        return offer_opening(progress, await self.settings.get(learner.id))

    async def card(
        self, learner: Learner, item_id: str, *, opening: bool = False, finish: bool = False
    ) -> None:
        """Открыта карточка; ``finish`` — заодно завершить начало занятия."""
        change: dict[str, Any] = {"screen_item_id": item_id, "screen_opening": opening}
        await self._change(learner, change | (_FINISHED if finish else {}))

    async def menu(self, learner: Learner, *, finish: bool = False) -> None:
        """На экране меню (главная, уроки, прогресс…): голосовое не оценивается."""
        await self._change(learner, _MENU | (_FINISHED if finish else {}))

    async def begin_opening(self, learner: Learner, resume_item: str, first_item: str) -> None:
        """Начать: куда вернуться после басмалы, местная дата, на экране — первая карточка."""
        s = await self.settings.get(learner.id)
        change = {
            "opening_resume_item": resume_item,
            "opening_day": self._today(s),
            "screen_item_id": first_item,
            "screen_opening": True,
        }
        await self._save(learner, s, change)

    async def skip_opening(self, learner: Learner) -> None:
        """«Пропустить» — сегодня (местная дата) больше не предлагать; на экране меню."""
        s = await self.settings.get(learner.id)
        change = _MENU | _FINISHED | {"opening_skipped_on": self._today(s)}
        await self._save(learner, s, change)

    def _today(self, s: LearnerSettings) -> date:
        return local_date(self.clock.now(), s.utc_offset_min)

    async def _change(self, learner: Learner, change: dict[str, Any]) -> None:
        await self._save(learner, await self.settings.get(learner.id), change)

    async def _save(self, learner: Learner, s: LearnerSettings, change: dict[str, Any]) -> None:
        diff = {k: v for k, v in change.items() if getattr(s, k) != v}
        if diff:  # ничего не изменилось — не писать; пишем только своё (ревью круга 2)
            await self.settings.change(learner.id, diff)
            await self.uow.commit()

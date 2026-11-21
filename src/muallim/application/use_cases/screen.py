"""Что на экране ученика — в БД, а не в памяти бота (TD-FN-90, ADR-0061).

Голосовое оценивается, только когда открыта карточка (решение автора 2026-10-20). Перезапуск бота
ничего не теряет (QAS-05, NFR-REL-01). Каждое изменение сохраняется сразу. «Начало занятия»
(ADR-0050) убрано автором 2026-11-21 — его колонки в БД остаются, здесь не читаются и не пишутся.
"""

from dataclasses import dataclass
from typing import Any, Final

from muallim.application.ports.repositories import LearnerSettingsRepository, UnitOfWork
from muallim.domain.learner import Learner
from muallim.domain.settings import LearnerSettings


@dataclass(frozen=True, slots=True)
class OnScreen:
    item_id: str | None  # None — на экране меню, не карточка
    sura: tuple[int, str] | None = None  # открыта сура целиком: (номер, text | look | memory)


SURA_SCREEN: Final = "sura:"  # экран суры хранится в том же поле, что карточка


def _sura_of(screen_item_id: str | None) -> tuple[int, str] | None:
    if not screen_item_id or not screen_item_id.startswith(SURA_SCREEN):
        return None
    number, _, mode = screen_item_id.removeprefix(SURA_SCREEN).partition(":")
    return (int(number), mode) if number.isdigit() and mode else None


_MENU: Final[dict[str, Any]] = {"screen_item_id": None}


@dataclass(frozen=True, slots=True)
class ScreenState:
    settings: LearnerSettingsRepository
    uow: UnitOfWork

    async def execute(self, learner: Learner) -> OnScreen:
        """Что сейчас на экране ученика."""
        s = await self.settings.get(learner.id)
        sura = _sura_of(s.screen_item_id)
        item_id = None if sura is not None else s.screen_item_id
        return OnScreen(item_id, sura)

    async def sura(self, learner: Learner, number: int, mode: str) -> None:
        """Открыта сура целиком (FR-57, FR-59): ``text`` — голосовое по тексту, ``look`` —
        наизусть, текст ещё виден (голосовое не принимаем), ``memory`` — наизусть после «Готов»."""
        await self._change(learner, {"screen_item_id": f"{SURA_SCREEN}{number}:{mode}"})

    async def card(self, learner: Learner, item_id: str) -> None:
        """Открыта карточка: голосовое оценивается по ней."""
        await self._change(learner, {"screen_item_id": item_id})

    async def menu(self, learner: Learner) -> None:
        """На экране меню (главная, уроки, прогресс…): голосовое не оценивается."""
        await self._change(learner, _MENU)

    async def _change(self, learner: Learner, change: dict[str, Any]) -> None:
        await self._save(learner, await self.settings.get(learner.id), change)

    async def _save(self, learner: Learner, s: LearnerSettings, change: dict[str, Any]) -> None:
        diff = {k: v for k, v in change.items() if getattr(s, k) != v}
        if diff:  # ничего не изменилось — не писать; пишем только своё (ревью круга 2)
            await self.settings.change(learner.id, diff)
            await self.uow.commit()

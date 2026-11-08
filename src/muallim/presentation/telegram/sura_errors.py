"""Список ошибок последнего чтения суры — у ученика в FSM, пока он разбирает аяты.

Автор 2026-11-08: после разбора аята — назад к списку ошибок суры, исправленные — ✅. Хранится в
памяти бота (MemoryStorage): после перезапуска списка нет — ученик читает суру ещё раз."""

from dataclasses import asdict, replace
from typing import Final

from aiogram.fsm.context import FSMContext

from muallim.presentation.telegram.screens import SuraErrorList

KEY: Final = "sura_errors"


async def remember(state: FSMContext, errors: SuraErrorList | None) -> None:
    """Сохранить список (None — сура прочитана чисто: списка больше нет)."""
    data = None if errors is None else asdict(errors) | {"fixed": sorted(errors.fixed)}
    await state.update_data({KEY: data})


async def load(state: FSMContext, sura: int | None = None) -> SuraErrorList | None:
    raw = (await state.get_data()).get(KEY)
    if not raw or (sura is not None and raw["sura"] != sura):
        return None
    return SuraErrorList(
        raw["sura"],
        raw["mode"],
        raw["clean"],
        raw["total"],
        tuple((int(n), str(i), str(o)) for n, i, o in raw["bad"]),
        frozenset(raw["fixed"]),
    )


async def sura_of(state: FSMContext, item_id: str) -> int | None:
    """Номер суры, если ``item_id`` — аят из её списка ошибок (на карточке — «📋 К ошибкам»)."""
    errors = await load(state)
    if errors is None or item_id not in {i for _, i, _ in errors.bad}:
        return None
    return errors.sura


async def mark_fixed(state: FSMContext, item_id: str) -> None:
    """Аят из списка прочитан верно — в списке он ✅."""
    errors = await load(state)
    if errors is not None and item_id in {i for _, i, _ in errors.bad}:
        await remember(state, replace(errors, fixed=errors.fixed | {item_id}))

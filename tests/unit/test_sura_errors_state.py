"""Список ошибок суры в FSM (автор 2026-11-08): сохраняется, ✅ исправленным, чисто — очищается."""

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from muallim.presentation.telegram import sura_errors
from muallim.presentation.telegram.screens import SuraErrorList

ERRORS = SuraErrorList(112, "m", 2, 4, ((2, "L123-03", "forgot_part"), (4, "L123-05", "skipped")))


def _state() -> FSMContext:
    return FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=2, user_id=3))


async def test_list_survives_and_marks_fixed_ayah() -> None:
    state = _state()
    await sura_errors.remember(state, ERRORS)
    assert await sura_errors.sura_of(state, "L123-03") == 112
    assert await sura_errors.sura_of(state, "L999-01") is None
    await sura_errors.mark_fixed(state, "L123-03")
    loaded = await sura_errors.load(state, 112)
    assert loaded is not None and loaded.fixed == {"L123-03"} and loaded.bad == ERRORS.bad
    assert await sura_errors.load(state, 1) is None  # другая сура


async def test_clean_reading_clears_the_list() -> None:
    state = _state()
    await sura_errors.remember(state, ERRORS)
    await sura_errors.remember(state, None)
    assert await sura_errors.load(state) is None

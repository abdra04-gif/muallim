"""Обработчики ученика. Тонкие: разобрать апдейт → вызвать сценарий → показать экран.

Разбиты по темам (docs/architecture/change-scenarios.md); порядок подключения важен — последний
обработчик ``voice.fallback`` ловит любое сообщение, поэтому ``voice`` подключается последним.
Состояние разговора (учитель ждёт эталон) — в FSM aiogram, экраны — через ``Display``.
"""

from typing import Final

from aiogram import Router

from muallim.presentation.telegram.handlers import commands, data, navigation, reference, voice

router: Final = Router(name="learner")
router.include_routers(
    commands.router, navigation.router, data.router, reference.router, voice.router
)

__all__ = ("router",)

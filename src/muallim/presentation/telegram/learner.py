"""Определение ученика по апдейту Telegram (dishka-провайдер уровня запроса)."""

from typing import NewType

from aiogram.types import User
from dishka import Provider, Scope, provide
from dishka.integrations.aiogram import AiogramMiddlewareData

from muallim.application.use_cases.learners import EnsureLearner
from muallim.domain.learner import Learner

NewLearner = NewType("NewLearner", bool)


class LearnerProvider(Provider):
    scope = Scope.REQUEST

    @provide
    async def learner_and_flag(
        self, data: AiogramMiddlewareData, ensure: EnsureLearner
    ) -> tuple[Learner, NewLearner]:
        user: User | None = data.get("event_from_user")
        if user is None or user.is_bot:
            raise RuntimeError("Апдейт без пользователя — ученика определить нельзя")
        learner, created = await ensure.execute(user.id, user.language_code)
        return learner, NewLearner(created)

    @provide
    def learner(self, pair: tuple[Learner, NewLearner]) -> Learner:
        return pair[0]

    @provide
    def is_new(self, pair: tuple[Learner, NewLearner]) -> NewLearner:
        return pair[1]

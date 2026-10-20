"""Кто видит служебное на экране результата: учитель или разметчик (FR-50).

Блок «Для исследования» с номером попытки новичку мешает, а учителю и разметчику нужен.
Сбой проверки разметчика (например, база недоступна) не должен лишать ученика результата:
тогда он просто не «staff».
"""

import logging
from dataclasses import dataclass
from typing import Final

from muallim.application.use_cases.annotation import AnnotatorAccess
from muallim.domain.learner import Learner

logger: Final = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class StaffAccess:
    teachers: frozenset[int]  # TEACHER_IDS
    annotators: AnnotatorAccess  # ANNOTATOR_IDS и приглашения

    async def is_staff(self, learner: Learner) -> bool:
        if learner.telegram_user_id in self.teachers:
            return True
        try:
            return await self.annotators.code_for(learner.telegram_user_id) is not None
        except Exception:  # любой сбой проверки = обычный ученик, результат он получит
            logger.warning("Не удалось проверить разметчика %s", learner.pseudonym, exc_info=True)
            return False

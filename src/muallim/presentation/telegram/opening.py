"""Начало занятия (ADR-0050): истиаза и басмала раз в день, двумя голосовыми подряд.

По правилам чтения допустимы четыре способа соединить истиазу, басмалу и начало чтения; лучший —
остановка после каждой (SRC-110; источник C — сверить с преподавателем, TD-FN-71). Поэтому
ученик читает по очереди две готовые карточки урока 1 (L001-02, L001-03) — попытки
сохраняются как обычные, программа не меняется.
Правило «предложить ли» — в ``domain/settings.py``, состояние (идёт ли, пропустил ли сегодня) —
в БД через сценарий ``ScreenState`` (ADR-0061): перезапуск бота его не теряет.
"""

from datetime import date
from typing import Final

from muallim.application.use_cases.progress import Progress
from muallim.application.use_cases.screen import offer_opening
from muallim.domain import settings as rules
from muallim.domain.settings import LearnerSettings

OPENING_ITEMS: Final = rules.OPENING_ITEMS  # истиаза, басмала
FIRST_LESSON: Final = rules.FIRST_LESSON


def needs_opening(progress: Progress, skipped_on: date | None) -> bool:
    """Предложить, если урок 1 пройден, сегодня ещё не занимался и сегодня не пропускал."""
    return offer_opening(progress, LearnerSettings(opening_skipped_on=skipped_on))

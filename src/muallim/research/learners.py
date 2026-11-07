"""Поиск ученика по номеру для личной помощи учителя (FR-65, ADR-0081).

Номер — псевдоним ``L-xxxxxxxx``, он есть во всех отчётах и выгрузках. По нему исследователь
узнаёт имя и анкету, чтобы помочь человеку лично. Telegram ID не показывается никогда.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from muallim.infrastructure.db.tables import (
    attempts,
    learner_names,
    learner_profiles,
    learners,
)


@dataclass(frozen=True, slots=True)
class LearnerCard:
    pseudonym: str
    display_name: str | None
    age_group: str | None
    gender: str | None
    native_language: str | None
    arabic_reading: str | None
    prayer: str | None
    research_consent: bool
    created_at: datetime
    attempts: int
    last_attempt_at: datetime | None


async def find(session: AsyncSession, pseudonym: str) -> LearnerCard | None:
    pseudonym = pseudonym.strip()
    if not pseudonym:
        return None
    query = (
        select(
            learners.c.pseudonym,
            learner_names.c.display_name,
            learner_profiles.c.age_group,
            learner_profiles.c.gender,
            learner_profiles.c.native_language,
            learner_profiles.c.arabic_reading,
            learner_profiles.c.prayer,
            learners.c.research_consent,
            learners.c.created_at,
            func.count(attempts.c.id).label("attempts"),
            func.max(attempts.c.created_at).label("last_attempt_at"),
        )
        .select_from(learners)
        .outerjoin(learner_names, learner_names.c.learner_id == learners.c.id)
        .outerjoin(learner_profiles, learner_profiles.c.learner_id == learners.c.id)
        .outerjoin(attempts, attempts.c.learner_id == learners.c.id)
        .where(learners.c.pseudonym == pseudonym)
        .group_by(learners.c.id, learner_names.c.display_name, *learner_profiles.c)
    )
    row = (await session.execute(query)).mappings().first()
    return LearnerCard(**row) if row else None


def render(card: LearnerCard) -> str:
    def shown(value: object) -> str:
        return "—" if value is None else str(value)

    last = card.last_attempt_at.isoformat(timespec="minutes") if card.last_attempt_at else "—"
    return "\n".join(
        [
            f"Ученик {card.pseudonym}",
            f"  Имя: {shown(card.display_name)}",
            f"  Возраст: {shown(card.age_group)}, пол: {shown(card.gender)}",
            f"  Родной язык: {shown(card.native_language)}, "
            f"арабский: {shown(card.arabic_reading)}, намаз: {shown(card.prayer)}",
            f"  Согласие на исследование: {'да' if card.research_consent else 'нет'}",
            f"  Попыток: {card.attempts}, последняя: {last}",
        ]
    )

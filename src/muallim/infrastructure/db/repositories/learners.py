from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from muallim.application.ports.repositories import LearnerProfileRepository, LearnerRepository
from muallim.domain.learner import (
    AgeGroup,
    ArabicReading,
    ConsentRecord,
    Gender,
    Learner,
    LearnerProfile,
    NativeLanguage,
    Prayer,
    Question,
)
from muallim.infrastructure.db.tables import consents, learner_names, learner_profiles, learners

_FIELDS = (
    "id",
    "telegram_user_id",
    "pseudonym",
    "language",
    "created_at",
    "current_item_id",
    "research_consent",
    "blocked_bot",
    "feedback_language",
)


def _row(learner: Learner) -> dict[str, Any]:
    return {name: getattr(learner, name) for name in _FIELDS}


@dataclass(frozen=True, slots=True)
class SqlLearnerRepository(LearnerRepository):
    session: AsyncSession

    async def get_by_telegram_id(self, telegram_user_id: int) -> Learner | None:
        query = select(learners).where(learners.c.telegram_user_id == telegram_user_id)
        row = (await self.session.execute(query)).mappings().first()
        return Learner(**{name: row[name] for name in _FIELDS}) if row else None

    async def add(self, learner: Learner) -> None:
        await self.session.execute(insert(learners).values(_row(learner)))

    async def save(self, learner: Learner) -> None:
        values = _row(learner)
        del values["id"]
        await self.session.execute(
            update(learners).where(learners.c.id == learner.id).values(values)
        )

    async def add_consent(self, record: ConsentRecord) -> None:
        await self.session.execute(
            insert(consents).values(
                learner_id=record.learner_id,
                kind=record.kind,
                granted=record.granted,
                text_version=record.text_version,
                at=record.at,
            )
        )

    async def delete(self, learner_id: UUID) -> None:
        # Попытки, ошибки, разметка и согласия удаляются каскадом (ON DELETE CASCADE).
        await self.session.execute(delete(learners).where(learners.c.id == learner_id))


@dataclass(frozen=True, slots=True)
class SqlLearnerProfileRepository(LearnerProfileRepository):
    session: AsyncSession

    async def get(self, learner_id: UUID) -> LearnerProfile | None:
        query = select(learner_profiles).where(learner_profiles.c.learner_id == learner_id)
        row = (await self.session.execute(query)).mappings().first()
        if row is None:
            return None
        name = await self.session.scalar(
            select(learner_names.c.display_name).where(learner_names.c.learner_id == learner_id)
        )
        return LearnerProfile(
            learner_id=row["learner_id"],
            questionnaire_version=row["questionnaire_version"],
            answered_at=row["answered_at"],
            display_name=name,
            age_group=_opt(AgeGroup, row["age_group"]),
            gender=_opt(Gender, row["gender"]),
            native_language=_opt(NativeLanguage, row["native_language"]),
            arabic_reading=_opt(ArabicReading, row["arabic_reading"]),
            prayer=_opt(Prayer, row["prayer"]),
            skipped=frozenset(Question(q) for q in row["skipped"] or ()),
        )

    async def save(self, profile: LearnerProfile) -> None:
        values = {
            "age_group": profile.age_group,
            "gender": profile.gender,
            "native_language": profile.native_language,
            "arabic_reading": profile.arabic_reading,
            "prayer": profile.prayer,
            "skipped": sorted(q.value for q in profile.skipped),
            "questionnaire_version": profile.questionnaire_version,
            "answered_at": profile.answered_at,
        }
        exists = await self.session.scalar(
            select(learner_profiles.c.learner_id).where(
                learner_profiles.c.learner_id == profile.learner_id
            )
        )
        if exists is None:
            await self.session.execute(
                insert(learner_profiles).values(learner_id=profile.learner_id, **values)
            )
        else:
            await self.session.execute(
                update(learner_profiles)
                .where(learner_profiles.c.learner_id == profile.learner_id)
                .values(**values)
            )
        if profile.display_name is not None:
            await self._save_name(profile.learner_id, profile.display_name)

    async def _save_name(self, learner_id: UUID, name: str) -> None:
        exists = await self.session.scalar(
            select(learner_names.c.learner_id).where(learner_names.c.learner_id == learner_id)
        )
        if exists is None:
            await self.session.execute(
                insert(learner_names).values(learner_id=learner_id, display_name=name)
            )
        else:
            await self.session.execute(
                update(learner_names)
                .where(learner_names.c.learner_id == learner_id)
                .values(display_name=name)
            )


def _opt[E: StrEnum](kind: type[E], value: str | None) -> E | None:
    return kind(value) if value else None

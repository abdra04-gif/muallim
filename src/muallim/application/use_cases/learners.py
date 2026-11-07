"""Регистрация ученика, согласие на исследование, анкета, удаление данных."""

from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import Any

from muallim.application.feedback import FeedbackCatalog
from muallim.application.ports.erasures import ErasureAction, ErasureLog
from muallim.application.ports.repositories import (
    AttemptRepository,
    LearnerProfileRepository,
    LearnerRepository,
    UnitOfWork,
)
from muallim.application.ports.storage import AudioStore
from muallim.application.ports.system import Clock, EventLog, IdGenerator
from muallim.domain.learner import (
    NAME_MAX_LENGTH,
    AgeGroup,
    ArabicReading,
    ConsentKind,
    ConsentRecord,
    Gender,
    Learner,
    LearnerProfile,
    NativeLanguage,
    Prayer,
    Question,
)

# Меняйте версию при каждом изменении текста согласия в presentation/telegram/texts.py.
CONSENT_TEXT_VERSION = "2026-11-07"
# Меняйте при изменении вопросов анкеты (presentation/telegram/texts.py, PROFILE_*).
QUESTIONNAIRE_VERSION = "2026-11-07"


@dataclass(frozen=True, slots=True)
class EnsureLearner:
    learners: LearnerRepository
    uow: UnitOfWork
    clock: Clock
    ids: IdGenerator
    events: EventLog

    async def execute(self, telegram_user_id: int, language: str | None) -> tuple[Learner, bool]:
        """Возвращает ученика и признак «зарегистрирован только что»."""
        learner = await self.learners.get_by_telegram_id(telegram_user_id)
        if learner is not None:
            if learner.blocked_bot:  # снова пишет боту — значит, разблокировал (ADR-0061 п. 4)
                learner.blocked_bot = False
                await self.learners.save(learner)
                await self.uow.commit()
            return learner, False
        learner_id = self.ids.new_id()
        learner = Learner(
            id=learner_id,
            telegram_user_id=telegram_user_id,
            pseudonym=f"L-{learner_id.hex[:8]}",
            language=(language or "ru")[:8],
            created_at=self.clock.now(),
        )
        await self.learners.add(learner)
        await self.events.record("learner_registered", learner.id, {})
        await self.uow.commit()
        return learner, True


@dataclass(frozen=True, slots=True)
class SetResearchConsent:
    """Согласие на запись голоса. Отзыв удаляет записи и разметку по ним (privacy.md)."""

    learners: LearnerRepository
    attempts: AttemptRepository
    audio: AudioStore
    uow: UnitOfWork
    clock: Clock
    events: EventLog
    erasures: ErasureLog

    async def execute(self, learner: Learner, granted: bool) -> None:
        # Отзыв — в журнал до commit (намерение не теряется); согласие — после (журнал не должен
        # утверждать согласие, которого нет в БД). ADR-0054.
        if not granted:
            await self.erasures.record(ErasureAction.WITHDRAW, learner.id)
        learner.research_consent = granted
        await self.learners.save(learner)
        released = [] if granted else await self.attempts.forget_audio(learner.id)
        await self.learners.add_consent(
            ConsentRecord(
                learner_id=learner.id,
                kind=ConsentKind.RESEARCH_AUDIO,
                granted=granted,
                text_version=CONSENT_TEXT_VERSION,
                at=self.clock.now(),
            )
        )
        await self.events.record(
            "consent_changed", learner.id, {"granted": int(granted), "audio_deleted": len(released)}
        )
        await self.uow.commit()
        if granted:
            await self.erasures.record(ErasureAction.GRANT, learner.id)
        await delete_unused_audio(released, self.attempts, self.audio)


_CHOICES: dict[
    Question, tuple[str, type[AgeGroup | Gender | NativeLanguage | ArabicReading | Prayer]]
] = {
    Question.AGE: ("age_group", AgeGroup),
    Question.GENDER: ("gender", Gender),
    Question.NATIVE: ("native_language", NativeLanguage),
    Question.READING: ("arabic_reading", ArabicReading),
    Question.PRAYER: ("prayer", Prayer),
}


def _parsed(question: Question, value: str) -> dict[str, Any] | None:
    """Поле профиля и его значение; None — ответ не из списка (старая кнопка, подделка)."""
    if question is Question.NAME:
        name = " ".join(value.split())  # без переводов строки и двойных пробелов
        return {"display_name": name} if 0 < len(name) <= NAME_MAX_LENGTH else None
    field, choices = _CHOICES[question]
    try:
        return {field: choices(value)}
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class Questionnaire:
    """Анкета один раз после согласия на исследование (FR-44, FR-65, ADR-0038, ADR-0081).

    Шесть вопросов, каждый можно пропустить; ответ сохраняется сразу, поэтому брошенная анкета
    продолжается с того же места. Без согласия на исследование анкета не нужна. Ответ не
    перезаписывается. Возраст «до 18» ничего не отключает (ADR-0081): голос пишется у всех.
    """

    profiles: LearnerProfileRepository
    uow: UnitOfWork
    clock: Clock
    events: EventLog

    async def next_question(self, learner: Learner) -> Question | None:
        profile = await self.profiles.get(learner.id)
        return Question.NAME if profile is None else profile.next_question()

    async def needed(self, learner: Learner) -> bool:
        return learner.research_consent and await self.next_question(learner) is not None

    async def answer(self, learner: Learner, question: Question, value: str) -> bool:
        """Сохраняет ответ; False — ответ не из списка или на вопрос уже отвечали."""
        fields = _parsed(question, value)
        profile = await self._profile(learner)
        if fields is None or profile.has_answer(question) or question in profile.skipped:
            return False
        await self.profiles.save(
            replace(
                profile,
                questionnaire_version=QUESTIONNAIRE_VERSION,
                answered_at=self.clock.now(),
                **fields,
            )
        )
        await self.events.record("questionnaire_answered", learner.id, {"question": question.value})
        return await self._finish(learner)

    async def skip(self, learner: Learner, question: Question) -> bool:
        profile = await self._profile(learner)
        if profile.has_answer(question) or question in profile.skipped:
            return False
        await self.profiles.save(
            replace(
                profile,
                questionnaire_version=QUESTIONNAIRE_VERSION,
                answered_at=self.clock.now(),
                skipped=profile.skipped | {question},
            )
        )
        await self.events.record("questionnaire_skipped", learner.id, {"question": question.value})
        return await self._finish(learner)

    async def _profile(self, learner: Learner) -> LearnerProfile:
        return await self.profiles.get(learner.id) or LearnerProfile(
            learner.id, QUESTIONNAIRE_VERSION, self.clock.now()
        )

    async def _finish(self, learner: Learner) -> bool:
        if await self.next_question(learner) is None:
            await self.events.record("questionnaire_completed", learner.id, {})
        await self.uow.commit()
        return True


@dataclass(frozen=True, slots=True)
class DeleteMyData:
    learners: LearnerRepository
    attempts: AttemptRepository
    audio: AudioStore
    uow: UnitOfWork
    events: EventLog
    erasures: ErasureLog

    async def execute(self, learner: Learner) -> None:
        await self.erasures.record(ErasureAction.DELETE, learner.id)
        hashes = await self.attempts.audio_hashes(learner.id)
        await self.learners.delete(learner.id)
        # Факт удаления фиксируем без привязки к ученику: его записи больше нет.
        await self.events.record("learner_deleted", None, {})
        await self.uow.commit()
        await delete_unused_audio(hashes, self.attempts, self.audio)


async def delete_unused_audio(
    hashes: Iterable[str], attempts: AttemptRepository, audio: AudioStore
) -> int:
    """Файлы — только после commit: при сбое БД не останется ссылок на удалённые записи.

    Ту же запись (тот же SHA-256) мог прислать другой ученик — её не трогаем. Если удаление
    файла сорвётся, `muallim-research verify` покажет его как лишний.
    """
    deleted = 0
    for sha in sorted(set(hashes)):
        if not await attempts.audio_in_use(sha):
            await audio.delete(sha)
            deleted += 1
    return deleted


@dataclass(frozen=True, slots=True)
class SetFeedbackLanguage:
    """Выбор языка объяснений ошибок (FR-22). Только среди включённых языков."""

    learners: LearnerRepository
    catalog: FeedbackCatalog
    uow: UnitOfWork
    events: EventLog

    async def execute(self, learner: Learner, code: str) -> bool:
        if code not in self.catalog.enabled():
            return False
        learner.feedback_language = code
        await self.learners.save(learner)
        await self.events.record("feedback_language_set", learner.id, {"language": code})
        await self.uow.commit()
        return True

"""Таблица ``quiz_answers`` (ADR-0066 п. 7, миграция 0009): одна строка — один показанный вопрос
«🧠 Закрепления», ответ дописывается в неё же один раз; удаляется вместе с учеником.
Идёт на SQLite и — при TEST_POSTGRES_URL — на PostgreSQL.
"""

from dataclasses import replace
from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from muallim.domain.learner import Learner
from muallim.domain.quiz import QuizAnswer
from muallim.infrastructure.db.repositories.learners import SqlLearnerRepository
from muallim.infrastructure.db.repositories.quiz import SqlQuizAnswerRepository
from muallim.infrastructure.db.tables import quiz_answers
from tests.fakes import FixedClock

pytestmark = pytest.mark.integration
LEARNER = UUID(int=1)


def _row(n: int, clock: FixedClock, *, round_no: int = 1) -> QuizAnswer:
    return QuizAnswer(
        id=UUID(int=100 + n),
        learner_id=LEARNER,
        round_no=round_no,
        position=n,
        step=2,
        letter_id="L007-05",
        item_id="L007-03",
        vowel=1,
        options=("تِ", "تَ", "مِ", "تُ"),
        answer=0,
        shown_at=clock.now(),
        curriculum_version="2026.10.21-book-5",
        rule="v2",
    )


async def _repo(session: AsyncSession) -> tuple[SqlQuizAnswerRepository, FixedClock]:
    clock = FixedClock()
    await SqlLearnerRepository(session).add(Learner(LEARNER, 77, "L-quiz", "ru", clock.now()))
    await session.commit()
    return SqlQuizAnswerRepository(session), clock


async def test_shown_question_round_trips(session: AsyncSession) -> None:
    repo, clock = await _repo(session)
    row = _row(1, clock)
    await repo.add(row)
    await session.commit()
    assert await repo.get(row.id) == row


async def test_answer_is_written_once(session: AsyncSession) -> None:
    repo, clock = await _repo(session)
    row = _row(1, clock)
    await repo.add(row)
    later = row.shown_at + timedelta(seconds=4)
    assert await repo.record(row.id, picked=0, correct=True, answered_at=later)
    assert not await repo.record(row.id, picked=2, correct=False, answered_at=later)
    await session.commit()
    saved = await repo.get(row.id)
    assert saved is not None
    assert (saved.picked, saved.correct, saved.answered_at) == (0, True, later)


async def test_unknown_row_is_not_recorded(session: AsyncSession) -> None:
    repo, clock = await _repo(session)
    assert not await repo.record(UUID(int=5), picked=0, correct=True, answered_at=clock.now())


async def test_history_is_in_round_and_position_order(session: AsyncSession) -> None:
    repo, clock = await _repo(session)
    for position, round_no in [(2, 1), (1, 2), (1, 1)]:
        row = _row(position, clock, round_no=round_no)
        await repo.add(replace(row, id=UUID(int=10 * round_no + position)))
    await session.commit()
    order = [(r.round_no, r.position) for r in await repo.history(LEARNER)]
    assert order == [(1, 1), (1, 2), (2, 1)]


async def test_rows_are_deleted_with_the_learner(session: AsyncSession) -> None:
    repo, clock = await _repo(session)
    await repo.add(_row(1, clock))
    await session.commit()
    await SqlLearnerRepository(session).delete(LEARNER)
    await session.commit()
    left = await session.scalar(select(func.count()).select_from(quiz_answers))
    assert left == 0


async def test_read_step_row_round_trips(session: AsyncSession) -> None:
    """Ступень ③: вариантов нет, верный — -1, причина отбора сохраняется."""
    repo, clock = await _repo(session)
    row = replace(_row(1, clock), step=3, item_id="L007-05", options=(), answer=-1, reason="due")
    await repo.add(row)
    await session.commit()
    saved = await repo.get(row.id)
    assert saved == row and saved is not None and saved.reason == "due"


async def test_one_question_per_place(session: AsyncSession) -> None:
    """UNIQUE (learner_id, round_no, position): двойное нажатие не даёт раунд из 11 вопросов."""
    repo, clock = await _repo(session)
    assert await repo.add(_row(1, clock))
    assert not await repo.add(replace(_row(1, clock), id=UUID(int=999)))
    await session.commit()
    assert len(await repo.history(LEARNER)) == 1

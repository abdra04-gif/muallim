"""Доступ разметчиков к разметке в Telegram (FR-17, ADR-0041): приглашение, отзыв, список.

Выдаёт и отзывает доступ только исследователь — командами ``muallim-research`` на своём
компьютере или сервере. В боте этого нет: посторонний не может ни попросить, ни выдать доступ.
"""

import secrets
from dataclasses import dataclass

from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from muallim.application.ports.system import Clock
from muallim.domain.annotation import INVITE_TTL, invite_digest, valid_annotator_code
from muallim.infrastructure.db.tables import annotator_invites, annotators

# Без похожих знаков (0/O, 1/I/L): код диктуют голосом или переписывают с экрана.
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_GROUPS, _GROUP = 3, 4  # «KQ7M-29FX-HT3P»: 12 знаков ≈ 59 бит — подобрать нельзя


def _check(code: str) -> None:
    if not valid_annotator_code(code):
        raise ValueError("Код разметчика: латиница, цифры, «-» и «_», до 64 символов (например A1)")


async def create_invite(session: AsyncSession, annotator: str, clock: Clock) -> str:
    """Новое приглашение на сутки, один вход. Если код был отозван — доступ снова откроется."""
    _check(annotator)
    code = "-".join(
        "".join(secrets.choice(_ALPHABET) for _ in range(_GROUP)) for _ in range(_GROUPS)
    )
    now = clock.now()
    await session.execute(
        insert(annotator_invites).values(
            code_digest=invite_digest(code), annotator=annotator, created_at=now,
            expires_at=now + INVITE_TTL,
        )
    )  # fmt: skip
    await session.execute(
        update(annotators).where(annotators.c.code == annotator).values(revoked_at=None)
    )
    await session.commit()
    return code


async def revoke(session: AsyncSession, annotator: str, clock: Clock) -> None:
    """Закрыть доступ сразу: и по приглашению, и из ANNOTATOR_IDS. Невошедшие приглашения гаснут."""
    _check(annotator)
    now = clock.now()
    found = await session.execute(select(annotators.c.code).where(annotators.c.code == annotator))
    if found.scalar_one_or_none() is None:
        await session.execute(insert(annotators).values(code=annotator, created_at=now))
    await session.execute(
        update(annotators).where(annotators.c.code == annotator).values(revoked_at=now)
    )
    await session.execute(
        delete(annotator_invites).where(
            annotator_invites.c.annotator == annotator, annotator_invites.c.used_at.is_(None)
        )
    )
    await session.commit()


@dataclass(frozen=True, slots=True)
class AnnotatorRow:
    code: str
    telegram_bound: bool  # вошёл по приглашению
    revoked: bool


async def list_annotators(session: AsyncSession) -> list[AnnotatorRow]:
    """Разметчики по приглашению и отозванные (список ANNOTATOR_IDS — в настройках)."""
    rows = await session.execute(
        select(annotators.c.code, annotators.c.telegram_user_id, annotators.c.revoked_at).order_by(
            annotators.c.code
        )
    )
    return [AnnotatorRow(c, tg is not None, at is not None) for c, tg, at in rows.all()]

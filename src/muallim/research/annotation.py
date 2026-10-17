"""Разметка попыток человеком: выгрузка очереди в CSV и загрузка результатов обратно.

Правила разметки и значения меток — docs/data/annotation-guide.md (GUIDE_VERSION ниже должна
совпадать с версией в документе; это проверяет тест).
"""

import csv
import json
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final
from uuid import UUID

from sqlalchemy import exists, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from muallim.application.ports.system import Clock
from muallim.infrastructure.db.tables import (
    annotations,
    attempts,
    detected_errors,
    learner_reports,
    learners,
)

GUIDE_VERSION: Final = "1.0"

EXPORT_COLUMNS: Final = (
    "attempt_id", "pseudonym", "item_id", "score", "verdict", "reference_phonemes",
    "heard_phonemes", "detected_errors", "learner_report", "audio_file",
    "label", "corrected_phonemes", "comment",
)  # fmt: skip


class AttemptLabel(StrEnum):
    CORRECT = "correct"  # модель права: вердикт и найденные ошибки верны
    FALSE_ALARM = "false_alarm"  # модель нашла ошибку, которой не было
    MISSED_ERROR = "missed_error"  # ученик ошибся, модель не заметила
    WRONG_ERROR = "wrong_error"  # ошибка была, но модель описала её не так
    AUDIO_UNUSABLE = "audio_unusable"  # шум, тишина, обрезано
    OFF_TASK = "off_task"  # прочитано не то, что на карточке


async def export_queue(session: AsyncSession, audio_root: Path, limit: int) -> list[dict[str, str]]:
    """Попытки с аудио, которые ещё никто не размечал.

    Первыми — оспоренные учеником («бот ошибся», ADR-0020), затем самые новые.
    """
    annotated = exists().where(annotations.c.attempt_id == attempts.c.id)
    report = (
        select(learner_reports.c.reason)
        .where(learner_reports.c.attempt_id == attempts.c.id)
        .order_by(learner_reports.c.created_at.desc())
        .limit(1)
        .scalar_subquery()
    )
    query = (
        select(attempts, learners.c.pseudonym, report.label("learner_report"))
        .join(learners, learners.c.id == attempts.c.learner_id)
        .where(
            attempts.c.audio_sha256.is_not(None),
            attempts.c.model_version != "stub",
            learners.c.research_consent.is_(True),
            ~annotated,
        )
        .order_by(report.is_(None), attempts.c.created_at.desc())
        .limit(limit)
    )
    rows = (await session.execute(query)).mappings().all()
    out = []
    for r in rows:
        errs = await session.execute(
            select(detected_errors.c.kind, detected_errors.c.expected, detected_errors.c.heard)
            .where(detected_errors.c.attempt_id == r["id"])
            .order_by(detected_errors.c.ordinal)
        )
        sha = r["audio_sha256"]
        out.append(
            {
                "attempt_id": str(r["id"]),
                "pseudonym": r["pseudonym"],
                "item_id": r["item_id"],
                "score": str(r["score"]),
                "verdict": r["verdict"],
                "reference_phonemes": r["reference_phonemes"],
                "heard_phonemes": r["heard_phonemes"],
                "learner_report": r["learner_report"] or "",
                "detected_errors": json.dumps(
                    [dict(e._mapping) for e in errs.all()], ensure_ascii=False
                ),
                "audio_file": str(audio_root / sha[:2] / f"{sha}.ogg"),
                "label": "",
                "corrected_phonemes": "",
                "comment": "",
            }
        )
    return out


def write_csv(rows: Iterable[dict[str, str]], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=EXPORT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


@dataclass(frozen=True, slots=True)
class ImportResult:
    imported: int
    skipped_empty: int


class AnnotationError(ValueError):
    pass


async def import_labels(
    session: AsyncSession, path: Path, annotator: str, clock: Clock
) -> ImportResult:
    """Загружает размеченный CSV. Строки без метки пропускаются; неверная метка — ошибка."""
    if not annotator or len(annotator) > 64:
        raise AnnotationError("Код разметчика обязателен (до 64 символов), например A1")
    imported = skipped = 0
    with path.open(encoding="utf-8", newline="") as f:
        for line_no, row in enumerate(csv.DictReader(f), start=2):
            label = (row.get("label") or "").strip()
            if not label:
                skipped += 1
                continue
            try:
                parsed = AttemptLabel(label)
                attempt_id = UUID(row["attempt_id"])
            except ValueError as error:
                raise AnnotationError(f"Строка {line_no}: {error}") from error
            await session.execute(
                insert(annotations).values(
                    attempt_id=attempt_id,
                    annotator=annotator,
                    label=parsed,
                    corrected_phonemes=(row.get("corrected_phonemes") or "").strip() or None,
                    comment=(row.get("comment") or "").strip(),
                    guide_version=GUIDE_VERSION,
                    created_at=clock.now(),
                )
            )
            imported += 1
    await session.commit()
    return ImportResult(imported, skipped)

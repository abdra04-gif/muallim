"""Выгрузка датасета для обучения/дообучения модели (FR-14).

В выгрузку попадают только ученики с согласием и только реальные попытки (не заглушка).
Telegram ID не выгружается никогда — только псевдоним.
"""

import json
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from muallim.infrastructure.db.tables import annotations, attempts, learners


async def dataset_rows(session: AsyncSession) -> list[dict[str, Any]]:
    query = (
        select(
            attempts.c.id,
            learners.c.pseudonym,
            attempts.c.item_id,
            attempts.c.curriculum_version,
            attempts.c.model_version,
            attempts.c.reference_phonemes,
            attempts.c.heard_phonemes,
            attempts.c.score,
            attempts.c.audio_sha256,
            attempts.c.audio_duration_ms,
            attempts.c.created_at,
            attempts.c.reference_variant,
            attempts.c.feedback_language,
            attempts.c.app_version,
            annotations.c.label,
            annotations.c.corrected_phonemes,
            annotations.c.annotator,
        )
        .join(learners, learners.c.id == attempts.c.learner_id)
        .outerjoin(
            annotations,
            (annotations.c.attempt_id == attempts.c.id) & annotations.c.detected_error_id.is_(None),
        )
        .where(
            learners.c.research_consent.is_(True),
            attempts.c.audio_sha256.is_not(None),
            attempts.c.model_version != "stub",
        )
        .order_by(attempts.c.created_at)
    )
    rows = []
    for r in (await session.execute(query)).mappings():
        row = dict(r)
        row["attempt_id"] = str(row.pop("id"))
        row["created_at"] = row["created_at"].isoformat()
        row["audio"] = f"audio/{row['audio_sha256']}.ogg"
        rows.append(row)
    return rows


def write_jsonl(rows: list[dict[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

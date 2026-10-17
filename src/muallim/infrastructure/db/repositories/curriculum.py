"""Снимок учебной программы: таблица curriculum_items (ADR-0023)."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from muallim.application.ports.repositories import CurriculumSnapshots, CurriculumVersionError
from muallim.domain.curriculum import Curriculum
from muallim.infrastructure.db.tables import curriculum_items

# Поля, по которым сравниваются версии: если они изменились, нужна новая версия программы.
_CONTENT = ("lesson_id", "position", "kind", "text", "note", "page", "line")


@dataclass
class SqlCurriculumSnapshots(CurriculumSnapshots):
    session: AsyncSession

    async def publish(self, curriculum: Curriculum) -> int:
        rows = _rows(curriculum)
        stored = (
            (
                await self.session.execute(
                    select(curriculum_items).where(
                        curriculum_items.c.curriculum_version == curriculum.version
                    )
                )
            )
            .mappings()
            .all()
        )
        if stored:
            old = {r["item_id"]: tuple(r[k] for k in _CONTENT) for r in stored}
            new = {r["item_id"]: tuple(r[k] for k in _CONTENT) for r in rows}
            changed = sorted(i for i in old.keys() | new.keys() if old.get(i) != new.get(i))
            if changed:
                raise CurriculumVersionError(
                    f"Программа {curriculum.version!r} изменилась без смены version: "
                    f"{', '.join(changed[:10])}. Увеличьте version в course.ru.yaml."
                )
            return 0
        now = datetime.now(UTC)
        await self.session.execute(
            insert(curriculum_items), [{**r, "published_at": now} for r in rows]
        )
        return len(rows)


def _rows(curriculum: Curriculum) -> list[dict[str, Any]]:
    rows = []
    for lesson in curriculum.lessons:
        for position, item in enumerate(lesson.items, start=1):
            src = item.source
            rows.append(
                {
                    "curriculum_version": curriculum.version,
                    "item_id": item.id,
                    "lesson_id": lesson.id,
                    "lesson_number": lesson.number,
                    "lesson_title": lesson.title,
                    "position": position,
                    "kind": str(item.kind),
                    "text": item.text,
                    "note": item.note,
                    "source_id": src.source_id if src else None,
                    "page": src.page if src else None,
                    "line": src.line if src else None,
                    "verified": bool(src and src.verified),
                }
            )
    return rows

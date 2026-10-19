"""Выгрузка датасета для оценки и дообучения модели (FR-14).

В выгрузку попадают только ученики с согласием и только реальные попытки (не заглушка).
Telegram ID не выгружается никогда — только псевдоним.

Строка — попытка: эталон, что услышала модель, и разметка каждого разметчика (последняя его
метка). ``consensus_phonemes`` — что прозвучало, если попытку оценили минимум двое разметчиков
и все записали одно и то же; иначе None — такие попытки сначала разбирают вместе
(docs/data/annotation-guide.md).
Для оценки по протоколу Iqra'Eval (``mdd_eval``) — ``truth.csv`` и ``predictions.csv``.
``phonemes.csv`` — разбор по каждому звуку для каждого разметчика: где модель права, где подняла
ложную тревогу, где пропустила ошибку (``metrics.phoneme_outcomes``, версия правила в столбце
``comparison_version``).
"""

import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from muallim.infrastructure.db.tables import annotations, attempts, learners
from muallim.research.annotation import USABLE, AttemptStatus
from muallim.research.metrics import COMPARISON_VERSION, phoneme_outcomes

_STATUSES = [str(s) for s in AttemptStatus]  # метки руководства 2.0; старые (без фонем) — нет


async def dataset_rows(session: AsyncSession) -> list[dict[str, Any]]:
    consenting_real = (
        learners.c.research_consent.is_(True),
        attempts.c.audio_sha256.is_not(None),
        attempts.c.model_version != "stub",
    )
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
        )
        .join(learners, learners.c.id == attempts.c.learner_id)
        .where(*consenting_real)
        .order_by(attempts.c.created_at, attempts.c.id)
    )
    labels = await session.execute(
        select(
            annotations.c.attempt_id, annotations.c.annotator, annotations.c.label,
            annotations.c.corrected_phonemes, annotations.c.guide_version,
            annotations.c.self_corrected,
        )
        .join(attempts, attempts.c.id == annotations.c.attempt_id)
        .join(learners, learners.c.id == attempts.c.learner_id)
        .where(*consenting_real, annotations.c.label.in_(_STATUSES))
        .order_by(annotations.c.created_at, annotations.c.id)
    )  # fmt: skip
    latest: dict[UUID, dict[str, dict[str, str | bool | None]]] = defaultdict(dict)
    for attempt_id, annotator, status, actual, guide, self_corrected in labels.all():
        latest[attempt_id][annotator] = {
            "annotator": annotator, "status": status, "actual_phonemes": actual,
            "guide_version": guide,
            "self_corrected": self_corrected,  # None — метка до руководства 2.1 (не спрашивали)
        }  # fmt: skip
    rows = []
    for r in (await session.execute(query)).mappings():
        row = dict(r)
        attempt_id = row.pop("id")
        marks = [latest[attempt_id][a] for a in sorted(latest.get(attempt_id, {}))]
        row["attempt_id"] = str(attempt_id)
        row["created_at"] = row["created_at"].isoformat()
        row["audio"] = f"audio/{row['audio_sha256']}.ogg"
        row["annotations"] = marks
        row["consensus_phonemes"] = _consensus(marks)
        rows.append(row)
    return rows


def _consensus(marks: list[dict[str, str | bool | None]]) -> str | None:
    actual = {str(m["actual_phonemes"]) for m in marks if m["actual_phonemes"] is not None}
    usable = len(marks) >= 2 and all(m["status"] in USABLE for m in marks)
    return actual.pop() if usable and len(actual) == 1 else None


def write_jsonl(rows: list[dict[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_iqraeval(rows: list[dict[str, Any]], out_dir: Path) -> None:
    """Файлы для ``mdd_eval`` Iqra'Eval: фонемы через пробел; только согласованная разметка."""
    agreed = [r for r in rows if r["consensus_phonemes"] is not None]
    tables: dict[str, tuple[tuple[str, ...], list[tuple[str, ...]]]] = {
        "truth.csv": (
            ("ID", "Reference_phn", "Annotated_phn"),
            [
                (
                    r["attempt_id"],
                    _spaced(r["reference_phonemes"]),
                    _spaced(r["consensus_phonemes"]),
                )
                for r in agreed
            ],
        ),
        "predictions.csv": (
            ("ID", "Prediction"),
            [(r["attempt_id"], _spaced(r["heard_phonemes"])) for r in agreed],
        ),
    }
    for name, (header, values) in tables.items():
        with (out_dir / name).open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(values)


PHONEME_COLUMNS = (
    "attempt_id", "item_id", "pseudonym", "model_version", "annotator", "position", "expected",
    "model_heard", "human_heard", "outcome", "same_diagnosis", "model_kind", "human_kind",
    "agrees_with_consensus", "self_corrected", "comparison_version",
)  # fmt: skip


def write_phonemes(rows: list[dict[str, Any]], path: Path) -> None:
    """По строке на каждый звук эталона для каждого разметчика, записавшего, что прозвучало.
    ``self_corrected`` — по попытке (отметил хоть один): такие попытки не входят в главные цифры
    отчёта (ADR-0044). BOM — чтобы Excel показал арабский текст."""
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(PHONEME_COLUMNS)
        for r in rows:
            for mark in r["annotations"]:
                actual = mark["actual_phonemes"]
                if mark["status"] not in USABLE or actual is None:
                    continue
                consensus = r["consensus_phonemes"]
                marked = [m["self_corrected"] for m in r["annotations"]]
                self_corrected = True if True in marked else None if None in marked else False
                for o in phoneme_outcomes(r["reference_phonemes"], r["heard_phonemes"], actual):
                    writer.writerow((
                        r["attempt_id"], r["item_id"], r["pseudonym"], r["model_version"],
                        mark["annotator"], o.position, o.expected, o.model_heard, o.human_heard,
                        o.outcome, _flag(o.same_diagnosis), o.model_kind or "", o.human_kind or "",
                        _flag(None if consensus is None else actual == consensus),
                        _flag(self_corrected), COMPARISON_VERSION,
                    ))  # fmt: skip


def _flag(value: bool | None) -> str:
    return "" if value is None else str(value).lower()


def _spaced(phonemes: str) -> str:
    return " ".join(phonemes)

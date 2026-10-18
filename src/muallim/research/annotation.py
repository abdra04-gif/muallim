"""Разметка попыток человеком: пакет для разметчика и загрузка результатов обратно.

Правила и метки — docs/data/annotation-guide.md (GUIDE_VERSION ниже должна совпадать с версией в
документе; это проверяет тест).

Пакет — папка: ``tasks.csv`` (UTF-8 с BOM — Excel и LibreOffice открывают без «кракозябр») и
``audio/`` с записями по относительным путям: папку можно отдать преподавателю, сервер не нужен.
Разметчик видит ответ бота (решение автора 2026-10-18): вердикт, найденные ошибки и что бот
услышал — поле «что прозвучало» уже заполнено этим. Бот прав — ``agree``, ошибся — ``fix`` и
исправить фонемы. В пакете все попытки, и засчитанные ботом тоже; где бот нашёл ошибки — в
начале. Риск «согласия по подсказке» — угроза валидности (docs/research/preregistration.md, §5).
Каждый разметчик получает свою очередь: всё размечают все, независимо друг от друга.
"""

import csv
import io
import re
import shutil
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final
from uuid import UUID

from sqlalchemy import and_, exists, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from muallim.application.ports.system import Clock
from muallim.domain.phonetics import CONSONANTS, SPECIAL, VOWELS
from muallim.domain.policy import Verdict
from muallim.infrastructure.audio.file_store import FileAudioStore
from muallim.infrastructure.db.tables import (
    annotations,
    attempts,
    curriculum_items,
    detected_errors,
    learner_reports,
    learners,
)

GUIDE_VERSION: Final = "2.0"

PACKAGE_COLUMNS: Final = (
    "n", "attempt_id", "annotator", "audio", "item_id", "item_text", "page", "line",
    "learner_says", "bot_verdict", "bot_errors", "reference_phonemes", "bot_heard",
    "actual_phonemes", "status", "comment",
)  # fmt: skip
_REQUIRED: Final = ("attempt_id", "annotator", "actual_phonemes", "status")
_LEARNER_SAYS: Final = {
    "read_correctly": "«я прочитал правильно»",
    "wrong_error": "«ошибка указана не та»",
    "other": "«бот ошибся»",
}

ALPHABET: Final = CONSONANTS | VOWELS | SPECIAL
# Частые описки при наборе арабского текста вместо фонетической записи (SRC-002).
_HINTS: Final = {
    **dict.fromkeys("أإآؤئ", "хамза пишется одним знаком «ء»"),
    "ّ": "удвоение пишется двумя одинаковыми буквами, без шадды",
    "ْ": "сукун не пишется: согласная без огласовки",
    **dict.fromkeys("ًٌٍ", "танвин пишется огласовкой и «ن»"),
}
# Невидимые знаки, которые добавляют Excel и редакторы (направление письма, BOM, пробелы).
_INVISIBLE: Final = str.maketrans(
    dict.fromkeys("\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069\ufeff", None)
)
_ANNOTATOR: Final = re.compile(r"[A-Za-z0-9_-]{1,64}")


class AttemptStatus(StrEnum):
    AGREE = "agree"  # бот услышал верно: actual_phonemes = что услышал бот
    FIX = "fix"  # бот ошибся: в actual_phonemes — что прозвучало на самом деле
    AUDIO_UNUSABLE = "audio_unusable"  # шум, тишина, обрезано, несколько голосов
    OFF_TASK = "off_task"  # прочитано не то, что на карточке


USABLE: Final = frozenset({AttemptStatus.AGREE, AttemptStatus.FIX})  # попытку можно оценить


class AnnotationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ImportResult:
    imported: int  # новых меток (в том числе исправления — прежние остаются в истории)
    unchanged: int = 0  # такая же метка этого разметчика уже есть
    skipped_empty: int = 0  # строка без status — разметчик её пропустил
    skipped_gone: int = 0  # ученик удалил данные или отозвал согласие


def _check_annotator(annotator: str) -> None:
    if not _ANNOTATOR.fullmatch(annotator):
        raise AnnotationError(
            "Код разметчика обязателен: латиница, цифры, «-» и «_», до 64 символов (например A1)"
        )


async def export_package(
    session: AsyncSession, audio_root: Path, out_dir: Path, annotator: str, limit: int
) -> int:
    """Пакет для разметчика: попытки с записью, которые он ещё не размечал. Возвращает их число."""
    _check_annotator(annotator)
    own = exists().where(
        annotations.c.attempt_id == attempts.c.id, annotations.c.annotator == annotator
    )
    disputed = exists().where(learner_reports.c.attempt_id == attempts.c.id)
    found_errors = exists().where(detected_errors.c.attempt_id == attempts.c.id)
    report = (
        select(learner_reports.c.reason)
        .where(learner_reports.c.attempt_id == attempts.c.id)
        .order_by(learner_reports.c.created_at.desc())
        .limit(1)
        .scalar_subquery()
    )
    query = (
        select(
            attempts.c.id, attempts.c.item_id, attempts.c.reference_phonemes,
            attempts.c.heard_phonemes, attempts.c.verdict, attempts.c.audio_sha256,
            curriculum_items.c.text, curriculum_items.c.page, curriculum_items.c.line,
            report.label("report"),
        )
        .join(learners, learners.c.id == attempts.c.learner_id)
        .outerjoin(
            curriculum_items,
            and_(
                curriculum_items.c.item_id == attempts.c.item_id,
                curriculum_items.c.curriculum_version == attempts.c.curriculum_version,
            ),
        )
        .where(
            attempts.c.audio_sha256.is_not(None),
            attempts.c.model_version != "stub",
            learners.c.research_consent.is_(True),
            ~own,
        )
        # Первыми — оспоренные учеником (ADR-0020), потом где бот нашёл ошибки, затем новые.
        .order_by(
            disputed.desc(), found_errors.desc(), attempts.c.created_at.desc(), attempts.c.id
        )
        .limit(limit)
    )  # fmt: skip
    rows = (await session.execute(query)).all()
    errors = await _bot_errors(session, [r.id for r in rows])
    store = FileAudioStore(audio_root)
    missing = [r.audio_sha256 for r in rows if not store.path_for(r.audio_sha256).is_file()]
    if missing:
        raise AnnotationError(
            f"Нет файлов записей: {len(missing)} (первый {missing[0]}). "
            "Проверьте хранилище: muallim-research verify"
        )
    # Копии голосов: папка и таблица — только владельцу, как data/audio (0700/0600).
    for folder in (out_dir, out_dir / "audio"):
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        folder.chmod(0o700)
    tasks = out_dir / "tasks.csv"
    tasks.touch(mode=0o600)
    tasks.chmod(0o600)
    with tasks.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=PACKAGE_COLUMNS)
        writer.writeheader()
        for n, r in enumerate(rows, start=1):
            audio = f"audio/{r.audio_sha256}.ogg"
            shutil.copy2(store.path_for(r.audio_sha256), out_dir / audio)
            writer.writerow(
                {
                    "n": n, "attempt_id": str(r.id), "annotator": annotator, "audio": audio,
                    "item_id": r.item_id, "item_text": r.text or "", "page": r.page or "",
                    "line": r.line or "", "learner_says": _LEARNER_SAYS.get(r.report or "", ""),
                    "bot_verdict": "не засчитано" if r.verdict == Verdict.FAILED else "засчитано",
                    "bot_errors": errors.get(r.id, ""), "reference_phonemes": r.reference_phonemes,
                    "bot_heard": r.heard_phonemes, "actual_phonemes": r.heard_phonemes,
                    "status": "", "comment": "",
                }
            )  # fmt: skip
    return len(rows)


async def _bot_errors(session: AsyncSession, ids: list[UUID]) -> dict[UUID, str]:
    """Ошибки, найденные ботом, коротко: «1) ص → س; 2) َ → —» (— — звука нет)."""
    found = await session.execute(
        select(detected_errors.c.attempt_id, detected_errors.c.expected, detected_errors.c.heard)
        .where(detected_errors.c.attempt_id.in_(ids))
        .order_by(detected_errors.c.attempt_id, detected_errors.c.ordinal)
    )
    parts: dict[UUID, list[str]] = {}
    for attempt_id, expected, heard in found.all():
        listed = parts.setdefault(attempt_id, [])
        listed.append(f"{len(listed) + 1}) {expected or '—'} → {heard or '—'}")
    return {attempt_id: "; ".join(items) for attempt_id, items in parts.items()}


@dataclass(frozen=True, slots=True)
class _Label:
    line_no: int
    attempt_id: UUID
    status: AttemptStatus
    actual: str | None
    comment: str


def clean_phonemes(text: str) -> str:
    """Без пробелов и невидимых знаков, которые добавляют Excel и редакторы."""
    return "".join(text.translate(_INVISIBLE).split())


def _parse(row: dict[str, str], line_no: int, annotator: str) -> _Label | None:
    status_text = (row.get("status") or "").strip()
    if not status_text:
        return None
    if (row.get("annotator") or "").strip() != annotator:
        raise AnnotationError(
            f"Строка {line_no}: пакет разметчика {row.get('annotator')!r}, а загружается "
            f"как {annotator!r}. Чужую разметку под своим кодом загружать нельзя."
        )
    try:
        status = AttemptStatus(status_text)
        attempt_id = UUID((row.get("attempt_id") or "").strip())
    except ValueError as error:
        allowed = ", ".join(AttemptStatus)
        raise AnnotationError(f"Строка {line_no}: {error} (метки: {allowed})") from error
    actual = clean_phonemes(row.get("actual_phonemes") or "")
    if status in USABLE:
        if not actual:
            raise AnnotationError(f"Строка {line_no}: пустое поле «что прозвучало»")
        for ch in actual:
            if ch not in ALPHABET:
                hint = _HINTS.get(ch, "в записи только буквы и огласовки фонетического алфавита")
                raise AnnotationError(f"Строка {line_no}: символ «{ch}» не фонема — {hint}")
    return _Label(
        line_no, attempt_id, status, actual if status in USABLE else None,
        (row.get("comment") or "").strip(),
    )  # fmt: skip


def _check_against_bot(label: _Label, heard: str) -> None:
    """«agree» — фонемы бота без правок, «fix» — с правками: иначе метка противоречит записи."""
    if label.status is AttemptStatus.AGREE and label.actual != heard:
        raise AnnotationError(
            f"Строка {label.line_no}: стоит «agree», но «что прозвучало» отличается от того, что "
            "услышал бот. Бот ошибся — поставьте «fix»; согласны — верните его вариант."
        )
    if label.status is AttemptStatus.FIX and label.actual == heard:
        raise AnnotationError(
            f"Строка {label.line_no}: стоит «fix», но ничего не исправлено. Если бот прав — "
            "поставьте «agree»."
        )


def _read(path: Path) -> list[dict[str, str]]:
    """CSV из пакета после Excel/LibreOffice: разделитель «,», «;» или табуляция, BOM или без."""
    text = path.read_text(encoding="utf-8-sig")
    header = text.split("\n", 1)[0]
    delimiter = max((",", ";", "\t"), key=header.count)
    reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=delimiter)
    missing = [c for c in _REQUIRED if c not in (reader.fieldnames or ())]
    if missing:
        raise AnnotationError(
            f"Не найдены колонки {', '.join(missing)}: загружайте tasks.csv из пакета разметки"
        )
    return list(reader)


async def import_package(
    session: AsyncSession, path: Path, annotator: str, clock: Clock
) -> ImportResult:
    """Загружает размеченный tasks.csv: всё или ничего (ошибка в строке — не сохраняется ничего).

    Повторная загрузка того же файла ничего не добавляет; исправленная метка добавляется новой
    строкой — история сохраняется, в метриках и датасете берётся последняя.
    """
    _check_annotator(annotator)
    parsed = [_parse(row, n, annotator) for n, row in enumerate(_read(path), start=2)]
    labels = [label for label in parsed if label is not None]
    ids = {label.attempt_id for label in labels}
    found = await session.execute(
        select(attempts.c.id, attempts.c.heard_phonemes)
        .join(learners, learners.c.id == attempts.c.learner_id)
        .where(
            attempts.c.id.in_(ids),
            attempts.c.audio_sha256.is_not(None),
            learners.c.research_consent.is_(True),
        )
    )
    heard = {attempt_id: phonemes for attempt_id, phonemes in found.all()}
    for label in labels:
        if label.attempt_id in heard:
            _check_against_bot(label, heard[label.attempt_id])
    previous = await session.execute(
        select(
            annotations.c.attempt_id, annotations.c.label, annotations.c.corrected_phonemes,
            annotations.c.comment,
        )
        .where(annotations.c.attempt_id.in_(ids), annotations.c.annotator == annotator)
        .order_by(annotations.c.created_at, annotations.c.id)
    )  # fmt: skip
    latest = {a: (status, actual, comment) for a, status, actual, comment in previous.all()}
    imported = unchanged = gone = 0
    for label in labels:
        if label.attempt_id not in heard:
            gone += 1
            continue
        if latest.get(label.attempt_id) == (label.status, label.actual, label.comment):
            unchanged += 1
            continue
        await session.execute(
            insert(annotations).values(
                attempt_id=label.attempt_id, annotator=annotator, label=label.status,
                corrected_phonemes=label.actual, comment=label.comment,
                guide_version=GUIDE_VERSION, created_at=clock.now(),
            )
        )  # fmt: skip
        latest[label.attempt_id] = (label.status, label.actual, label.comment)
        imported += 1
    await session.commit()
    return ImportResult(imported, unchanged, len(parsed) - len(labels), gone)

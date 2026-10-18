"""Разметка попыток человеком: пакет для разметчика и загрузка результатов обратно.

Правила и метки — docs/data/annotation-guide.md; GUIDE_VERSION — в domain/annotation.py (совпадает
с версией в документе; это проверяет тест). Те же правила — у разметки в Telegram (FR-17).

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
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Final
from uuid import UUID

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from muallim.application.ports.system import Clock
from muallim.domain.annotation import (
    GUIDE_VERSION,
    PHONEME_ALPHABET,
    USABLE,
    AnnotationSource,
    LabelError,
    check_label,
    check_phonemes,
    check_self_correction,
    clean_phonemes,
    valid_annotator_code,
)
from muallim.domain.annotation import AnnotationStatus as AttemptStatus
from muallim.domain.policy import Verdict
from muallim.infrastructure.audio.file_store import FileAudioStore
from muallim.infrastructure.db.repositories.annotation import bot_errors, queue_query
from muallim.infrastructure.db.tables import annotations, attempts, learners

__all__ = [
    "ALPHABET", "GUIDE_VERSION", "PACKAGE_COLUMNS", "USABLE", "AnnotationError", "AttemptStatus",
    "ImportResult", "clean_phonemes", "export_package", "import_package",
]  # fmt: skip

PACKAGE_COLUMNS: Final = (
    "n", "attempt_id", "annotator", "audio", "item_id", "item_text", "page", "line",
    "learner_says", "bot_verdict", "bot_errors", "reference_phonemes", "bot_heard",
    "actual_phonemes", "status", "self_corrected", "comment",
)  # fmt: skip
# «Сам исправился» (руководство 2.1): «да» — ученик ошибся и сам перечитал верно; пусто — нет.
_YES: Final = frozenset({"да", "1", "yes", "y", "+"})
_NO: Final = frozenset({"", "нет", "0", "no", "n", "-"})
_REQUIRED: Final = ("attempt_id", "annotator", "actual_phonemes", "status")
_LEARNER_SAYS: Final = {
    "read_correctly": "«я прочитал правильно»",
    "wrong_error": "«ошибка указана не та»",
    "other": "«бот ошибся»",
}

ALPHABET: Final = PHONEME_ALPHABET


class AnnotationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ImportResult:
    imported: int  # новых меток (в том числе исправления — прежние остаются в истории)
    unchanged: int = 0  # такая же метка этого разметчика уже есть
    skipped_empty: int = 0  # строка без status — разметчик её пропустил
    skipped_gone: int = 0  # ученик удалил данные или отозвал согласие


def _check_annotator(annotator: str) -> None:
    if not valid_annotator_code(annotator):
        raise AnnotationError(
            "Код разметчика обязателен: латиница, цифры, «-» и «_», до 64 символов (например A1)"
        )


async def export_package(
    session: AsyncSession, audio_root: Path, out_dir: Path, annotator: str, limit: int
) -> int:
    """Пакет для разметчика: попытки с записью, которые он ещё не размечал. Возвращает их число."""
    _check_annotator(annotator)
    query = queue_query(annotator).limit(limit)
    rows = (await session.execute(query)).all()
    found = await bot_errors(session, [r.id for r in rows])
    errors = {a: _errors_text(e) for a, e in found.items()}
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
                    "status": "", "self_corrected": "", "comment": "",
                }
            )  # fmt: skip
    return len(rows)


def _errors_text(found: tuple[tuple[str, str], ...]) -> str:
    """Ошибки, найденные ботом, коротко: «1) ص → س; 2) َ → —» (— — звука нет)."""
    return "; ".join(f"{n}) {e or '—'} → {h or '—'}" for n, (e, h) in enumerate(found, start=1))


@dataclass(frozen=True, slots=True)
class _Label:
    line_no: int
    attempt_id: UUID
    status: AttemptStatus
    actual: str | None
    comment: str
    self_corrected: bool


def _self_corrected(row: dict[str, str], line_no: int, status: AttemptStatus) -> bool:
    """Колонки может не быть (пакет до руководства 2.1) — тогда «нет»."""
    value = (row.get("self_corrected") or "").strip().lower()
    if value not in _YES | _NO:
        raise AnnotationError(f"Строка {line_no}: self_corrected — «да» или пусто, а не {value!r}")
    flag = value in _YES
    try:
        check_self_correction(status, self_corrected=flag)
    except LabelError as error:
        raise AnnotationError(f"Строка {line_no}: {error}") from error
    return flag


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
        try:
            check_phonemes(actual)
        except LabelError as error:
            raise AnnotationError(f"Строка {line_no}: {error}") from error
    return _Label(
        line_no, attempt_id, status, actual if status in USABLE else None,
        (row.get("comment") or "").strip(), _self_corrected(row, line_no, status),
    )  # fmt: skip


def _check_against_bot(label: _Label, heard: str) -> None:
    try:
        check_label(label.status, label.actual, heard)
    except LabelError as error:
        raise AnnotationError(f"Строка {label.line_no}: {error}") from error


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
    heard = dict(found.tuples().all())
    for label in labels:
        if label.attempt_id in heard:
            _check_against_bot(label, heard[label.attempt_id])
    previous = await session.execute(
        select(
            annotations.c.attempt_id, annotations.c.label, annotations.c.corrected_phonemes,
            annotations.c.comment, annotations.c.self_corrected,
        )
        .where(annotations.c.attempt_id.in_(ids), annotations.c.annotator == annotator)
        .order_by(annotations.c.created_at, annotations.c.id)
    )  # fmt: skip
    latest = {
        a: (status, actual, comment, bool(flag))
        for a, status, actual, comment, flag in previous.all()
    }
    imported = unchanged = gone = 0
    for label in labels:
        if label.attempt_id not in heard:
            gone += 1
            continue
        mark = (label.status, label.actual, label.comment, label.self_corrected)
        if latest.get(label.attempt_id) == mark:
            unchanged += 1
            continue
        await session.execute(
            insert(annotations).values(
                attempt_id=label.attempt_id, annotator=annotator, label=label.status,
                corrected_phonemes=label.actual, comment=label.comment,
                guide_version=GUIDE_VERSION, source=AnnotationSource.EXCEL, created_at=clock.now(),
                self_corrected=label.self_corrected,
            )
        )  # fmt: skip
        latest[label.attempt_id] = mark
        imported += 1
    await session.commit()
    return ImportResult(imported, unchanged, len(parsed) - len(labels), gone)

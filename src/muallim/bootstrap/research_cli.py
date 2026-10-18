"""``uv run muallim-research <команда>`` — инструменты для работы с данными исследования.

Команды:
  report                         Markdown-отчёт в analytics/reports/ (SQL-отчёты + метрики GQM)
  annotation-export --annotator A1 [--limit N]
                                 пакет разметчика: data/annotation/A1_<дата>/ (tasks.csv + audio/)
  annotation-import FILE --annotator A1
                                 загрузить размеченный tasks.csv (docs/data/annotation-guide.md)
  dataset-export                 manifest.jsonl + truth.csv/predictions.csv (Iqra'Eval) + аудио
                                 в data/exports/<дата>/
  verify [--delete-orphans]      сверка БД и файлов записей: потери, лишние, повреждённые
  errors [фильтры]               каталог ошибок: таблица на экран + CSV в data/errors/
                                 (muallim-research errors --help — все фильтры)
"""

import argparse
import asyncio
import shutil
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from muallim.bootstrap.config import PROJECT_ROOT, Settings
from muallim.infrastructure.audio.file_store import FileAudioStore
from muallim.infrastructure.db.engine import create_engine, create_session_factory
from muallim.infrastructure.system import SystemClock
from muallim.research import annotation, dataset, errors, integrity, metrics, reports


async def _run(args: argparse.Namespace) -> str:
    settings = Settings()
    engine = create_engine(settings.database_url.get_secret_value())
    clock = SystemClock()
    stamp = clock.now().strftime("%Y-%m-%d_%H%M%S")
    try:
        if args.command == "report":
            out = PROJECT_ROOT / "analytics" / "reports" / f"report_{stamp}.md"
            sql = await reports.build_report(
                engine, PROJECT_ROOT / "analytics" / "sql", clock.now()
            )
            async with create_session_factory(engine)() as session:
                gqm = metrics.render(await metrics.collect(session, clock.now().date()))
            out.write_text(f"{sql}\n{gqm}", encoding="utf-8")
            return f"Отчёт: {out}"
        async with create_session_factory(engine)() as session:
            if args.command == "annotation-export":
                out = PROJECT_ROOT / "data" / "annotation" / f"{args.annotator}_{stamp}"
                count = await annotation.export_package(
                    session, settings.audio_dir, out, args.annotator, args.limit
                )
                return f"Разметчику {args.annotator}: {count} попыток → {out}"
            if args.command == "annotation-import":
                r = await annotation.import_package(session, args.file, args.annotator, clock)
                return (
                    f"Загружено меток: {r.imported}; без изменений: {r.unchanged}; "
                    f"пустых строк: {r.skipped_empty}; пропущено (ученик удалил данные или "
                    f"отозвал согласие): {r.skipped_gone}"
                )
            if args.command == "verify":
                copies = [PROJECT_ROOT / "data" / "annotation", PROJECT_ROOT / "data" / "exports"]
                report = await integrity.check(session, settings.audio_dir, copies)
                text = integrity.render(report)
                if args.delete_orphans and report.orphans:
                    deleted = await integrity.delete_orphans(session, report, settings.audio_dir)
                    text += f"\nУдалено лишних файлов (старше 10 минут): {deleted}"
                return text
            if args.command == "errors":
                return await _errors(session, args, settings, stamp)
            if args.command == "dataset-export":
                rows = await dataset.dataset_rows(session)
                store = FileAudioStore(settings.audio_dir)
                missing = [r for r in rows if not store.path_for(r["audio_sha256"]).is_file()]
                if missing:  # до создания папки: недоделанная выгрузка хуже, чем никакой
                    raise annotation.AnnotationError(
                        f"Нет файлов записей: {len(missing)}. Сначала: muallim-research verify"
                    )
                out_dir = PROJECT_ROOT / "data" / "exports" / stamp
                (out_dir / "audio").mkdir(parents=True)
                for row in rows:
                    shutil.copy2(store.path_for(row["audio_sha256"]), out_dir / row["audio"])
                dataset.write_jsonl(rows, out_dir / "manifest.jsonl")
                dataset.write_iqraeval(rows, out_dir)
                agreed = sum(r["consensus_phonemes"] is not None for r in rows)
                return f"Датасет: {len(rows)} записей, согласованная разметка: {agreed} → {out_dir}"
    finally:
        await engine.dispose()
    raise SystemExit(f"Неизвестная команда {args.command}")


async def _errors(
    session: AsyncSession, args: argparse.Namespace, settings: Settings, stamp: str
) -> str:
    flt = errors.ErrorFilter(
        expected=args.letter, heard=args.heard, kind=args.kind, lesson=args.lesson,
        item=args.item, page=args.page, line=args.line, learner=args.learner,
        since=_date(args.since), until=_date(args.until), minimal_pairs=args.pairs,
        unannotated=args.unannotated, disputed=args.disputed, with_audio=args.with_audio,
        include_stub=args.include_stub, limit=args.limit,
    )  # fmt: skip
    rows = await errors.find_errors(session, flt)
    out = PROJECT_ROOT / "data" / "errors" / f"errors_{stamp}.csv"
    errors.write_csv(rows, out, settings.audio_dir)
    shown = ("created_at", "pseudonym", "page", "line", "item_text", "kind", "expected", "heard")
    table = reports.to_markdown_table(
        shown,
        [tuple(str(r[c])[:19] if c == "created_at" else r[c] for c in shown) for r in rows[:30]],
    )
    return f"{table}\n\nНайдено ошибок: {len(rows)} (на экране до 30) → {out}"


def _date(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value).replace(tzinfo=UTC) if value else None


def main() -> None:
    parser = argparse.ArgumentParser(prog="muallim-research", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("report")
    exp = sub.add_parser("annotation-export")
    exp.add_argument("--annotator", required=True, help="код разметчика, например A1")
    exp.add_argument("--limit", type=int, default=100)
    imp = sub.add_parser("annotation-import")
    imp.add_argument("file", type=Path)
    imp.add_argument("--annotator", required=True)
    sub.add_parser("dataset-export")
    ver = sub.add_parser("verify", help="сверка БД и файлов записей")
    ver.add_argument(
        "--delete-orphans", action="store_true", help="удалить файлы, на которые нет попыток"
    )
    err = sub.add_parser("errors", help="каталог ошибок с фильтрами")
    err.add_argument("--letter", help="какая буква должна была прозвучать, например ص")
    err.add_argument("--heard", help="что услышала модель, например س")
    err.add_argument("--kind", help="тип ошибки, например letter_substitution")
    err.add_argument("--lesson", help="урок, например L18")
    err.add_argument("--item", help="карточка, например L18-02")
    err.add_argument("--page", type=int, help="страница книги")
    err.add_argument("--line", type=int, help="строка на странице")
    err.add_argument("--learner", help="псевдоним ученика, L-xxxx")
    err.add_argument("--since", help="с даты, ГГГГ-ММ-ДД")
    err.add_argument("--until", help="до даты (не включая), ГГГГ-ММ-ДД")
    err.add_argument("--pairs", action="store_true", help="только строки «Обратите внимание»")
    err.add_argument("--unannotated", action="store_true", help="ещё не размеченные")
    err.add_argument("--disputed", action="store_true", help="ученик нажал «Бот ошибся»")
    err.add_argument("--with-audio", action="store_true", help="только с записью")
    err.add_argument("--include-stub", action="store_true", help="включить попытки-заглушки")
    err.add_argument("--limit", type=int, default=500)
    try:
        print(asyncio.run(_run(parser.parse_args())))
    except annotation.AnnotationError as error:
        raise SystemExit(f"Ошибка: {error}") from None

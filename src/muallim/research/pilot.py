"""Метрики пилота (FR-55, docs/research/metrics-gqm.md): продвижение по книге и путь новичка (G4),
повтор после объяснения (G3, разведка E-7), время ответа по дням (G5).

Формулы — чистые функции над попытками (``Try``); ``collect`` берёт их из БД через SQLAlchemy Core
(SQLite в тестах, PostgreSQL в работе). Заглушка не входит. Зачёт — по вердикту, сохранённому ботом
с порогами той попытки, а не по нынешнему порогу. Время — UTC, неделя — с понедельника. В отчёте
только агрегаты: ни Telegram ID, ни псевдонимов.
"""

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from itertools import pairwise
from statistics import fmean, median
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from muallim.domain.policy import Verdict
from muallim.infrastructure.db.tables import (
    attempts,
    curriculum_items,
    detected_errors,
    interaction_events,
    learners,
)
from muallim.research.metrics import STUB, nearest_rank
from muallim.research.reports import to_markdown_table

IDLE_DAYS = 7  # столько дней без попыток — ученик «ушёл» (Q4.3)
ALL, WITH_REFERENCE, WITHOUT_REFERENCE = "все", "с эталоном 🔊", "без эталона"
NO_DATA = "нет данных"


@dataclass(frozen=True, slots=True)
class Try:
    """Попытка чтения для метрик пилота. ``errors`` — названные ботом: (позиция, нужный звук)."""

    learner: str
    item_id: str
    lesson: int | None  # из снимка программы; None — снимка нет
    at: datetime
    score: int
    passed: bool
    reference: str
    errors: frozenset[tuple[int, str]]


def _utc_day(moment: datetime) -> date:
    return (moment.astimezone(UTC) if moment.tzinfo else moment).date()


def _by_line(tries: Iterable[Try]) -> dict[tuple[str, str], list[Try]]:
    """Попытки ученика по строке, по времени."""
    lines: dict[tuple[str, str], list[Try]] = defaultdict(list)
    for t in tries:
        lines[(t.learner, t.item_id)].append(t)
    for series in lines.values():
        series.sort(key=lambda t: t.at)
    return lines


# ---------- Q4.4 главная метрика ----------
@dataclass(frozen=True, slots=True)
class WeekLines:
    week: date  # понедельник
    lines: int  # строк книги, впервые засчитанных за неделю (по ученику)
    learners: int  # учеников, у которых такие строки есть


def weekly_new_lines(tries: Iterable[Try]) -> list[WeekLines]:
    lines: Counter[date] = Counter()
    who: dict[date, set[str]] = defaultdict(set)
    for (learner, _), series in _by_line(tries).items():
        first = next((t for t in series if t.passed), None)
        if first is None:
            continue
        day = _utc_day(first.at)
        week = day - timedelta(days=day.weekday())
        lines[week] += 1
        who[week].add(learner)
    return [WeekLines(week, lines[week], len(who[week])) for week in sorted(lines)]


# ---------- Q4.1 первый успех ----------
@dataclass(frozen=True, slots=True)
class FirstSuccess:
    learners: int
    passed_ever: int
    passed_same_day: int  # первый зачёт — в день регистрации (UTC)
    median_minutes: float | None  # от регистрации до первого зачёта

    @property
    def same_day_share(self) -> float | None:
        return self.passed_same_day / self.learners if self.learners else None


def first_success(registered: Mapping[str, datetime], tries: Iterable[Try]) -> FirstSuccess:
    first: dict[str, datetime] = {}
    for t in tries:
        if t.passed and (t.learner not in first or t.at < first[t.learner]):
            first[t.learner] = t.at
    minutes = []
    same_day = 0
    for learner, joined in registered.items():
        if (at := first.get(learner)) is None:
            continue
        minutes.append((at - joined).total_seconds() / 60)
        same_day += _utc_day(at) == _utc_day(joined)
    return FirstSuccess(
        len(registered), len(minutes), same_day, float(median(minutes)) if minutes else None
    )


# ---------- Q4.3 где бросают ----------
def drop_off(tries: Iterable[Try], today: date) -> dict[int | None, int]:
    """Урок последней попытки у тех, кто не занимался ``IDLE_DAYS`` и больше дней."""
    last: dict[str, Try] = {}
    for t in tries:
        if t.learner not in last or t.at > last[t.learner].at:
            last[t.learner] = t
    gone: Counter[int | None] = Counter(
        t.lesson for t in last.values() if (today - _utc_day(t.at)).days >= IDLE_DAYS
    )
    return dict(gone)


# ---------- Q4.5 попыток до зачёта ----------
@dataclass(frozen=True, slots=True)
class LessonEffort:
    passed: int  # строк (по ученику), засчитанных хотя бы раз
    median_attempts: float | None  # попыток до первого зачёта включительно
    not_passed: int  # строк, которые так и не засчитаны


def attempts_to_pass(tries: Iterable[Try]) -> dict[int, LessonEffort]:
    needed: dict[int, list[int]] = defaultdict(list)
    failed: Counter[int] = Counter()
    for series in _by_line(tries).values():
        lesson = series[0].lesson
        if lesson is None:
            continue
        n = next((i for i, t in enumerate(series, start=1) if t.passed), None)
        if n is None:
            failed[lesson] += 1
        else:
            needed[lesson].append(n)
    return {
        lesson: LessonEffort(
            len(needed[lesson]),
            float(median(needed[lesson])) if needed[lesson] else None,
            failed[lesson],
        )
        for lesson in sorted(set(needed) | set(failed))
    }


# ---------- Q3.1–Q3.3 повтор после объяснения ----------
@dataclass(frozen=True, slots=True)
class RetryEffect:
    pairs: int  # незасчитанная попытка и следующая по той же строке
    mean_delta: float | None  # средний прирост балла
    improved: int  # балл вырос
    named: int  # ошибок, названных ботом в первой попытке пары (тот же эталон)
    fixed: int  # …и во второй попытке их там нет

    @property
    def improved_share(self) -> float | None:
        return self.improved / self.pairs if self.pairs else None

    @property
    def fixed_share(self) -> float | None:
        return self.fixed / self.named if self.named else None


def _effect(pairs: Sequence[tuple[Try, Try]]) -> RetryEffect:
    deltas = [b.score - a.score for a, b in pairs]
    named = fixed = 0
    for a, b in pairs:
        if a.reference != b.reference:  # другой вариант эталона — позиции несравнимы
            continue
        named += len(a.errors)
        fixed += len(a.errors - b.errors)
    return RetryEffect(
        len(pairs), fmean(deltas) if deltas else None, sum(d > 0 for d in deltas), named, fixed
    )


def retries(
    tries: Iterable[Try], played: Mapping[tuple[str, str], Sequence[datetime]]
) -> dict[str, RetryEffect]:
    """Q3.3: «с эталоном» — эталон 🔊 этой строки прослушан между попытками пары."""
    split: dict[str, list[tuple[Try, Try]]] = {ALL: [], WITH_REFERENCE: [], WITHOUT_REFERENCE: []}
    for key, series in _by_line(tries).items():
        for a, b in pairwise(series):
            if a.passed:
                continue
            listened = any(a.at < at < b.at for at in played.get(key, ()))
            split[ALL].append((a, b))
            split[WITH_REFERENCE if listened else WITHOUT_REFERENCE].append((a, b))
    return {name: _effect(pairs) for name, pairs in split.items()}


# ---------- Q5.1 время ответа по дням ----------
@dataclass(frozen=True, slots=True)
class DayTiming:
    day: date
    attempts: int
    p50_ms: int | None
    p90_ms: int | None
    max_ms: int | None


def response_by_day(rows: Iterable[tuple[datetime, int]]) -> list[DayTiming]:
    days: dict[date, list[int]] = defaultdict(list)
    for at, ms in rows:
        days[_utc_day(at)].append(ms)
    return [
        DayTiming(day, len(v), nearest_rank(v, 50), nearest_rank(v, 90), max(v))
        for day, v in sorted(days.items())
    ]


# ---------- сбор из БД ----------
@dataclass(frozen=True, slots=True)
class PilotReport:
    weekly: list[WeekLines]
    first_success: FirstSuccess
    drop_off: dict[int | None, int]
    effort: dict[int, LessonEffort]
    retries: dict[str, RetryEffect]
    response: list[DayTiming]


async def collect(session: AsyncSession, today: date) -> PilotReport:
    real = attempts.c.model_version != STUB
    rows = (
        await session.execute(
            select(
                attempts.c.id, attempts.c.learner_id, attempts.c.item_id,
                curriculum_items.c.lesson_number, attempts.c.created_at, attempts.c.score,
                attempts.c.verdict, attempts.c.reference_phonemes, attempts.c.processing_ms,
            )
            .outerjoin(
                curriculum_items,
                and_(
                    curriculum_items.c.item_id == attempts.c.item_id,
                    curriculum_items.c.curriculum_version == attempts.c.curriculum_version,
                ),
            )
            .where(real)
        )
    ).all()  # fmt: skip
    named: dict[UUID, set[tuple[int, str]]] = defaultdict(set)
    found = await session.execute(
        select(detected_errors.c.attempt_id, detected_errors.c.position, detected_errors.c.expected)
        .join(attempts, attempts.c.id == detected_errors.c.attempt_id)
        .where(real)
    )
    for attempt_id, position, expected in found.all():
        named[attempt_id].add((position, expected))
    tries = [
        Try(
            str(r.learner_id), r.item_id, r.lesson_number, r.created_at, r.score,
            r.verdict != Verdict.FAILED, r.reference_phonemes, frozenset(named[r.id]),
        )
        for r in rows
    ]  # fmt: skip
    registered = {
        str(learner_id): joined
        for learner_id, joined in (
            await session.execute(select(learners.c.id, learners.c.created_at))
        ).all()
    }
    played: dict[tuple[str, str], list[datetime]] = defaultdict(list)
    events = await session.execute(
        select(
            interaction_events.c.learner_id,
            interaction_events.c.payload,
            interaction_events.c.created_at,
        ).where(interaction_events.c.event == "reference_played")
    )
    for learner_id, payload, at in events.all():
        item = (payload or {}).get("item_id")
        if learner_id is not None and item:
            played[(str(learner_id), str(item))].append(at)
    return PilotReport(
        weekly_new_lines(tries),
        first_success(registered, tries),
        drop_off(tries, today),
        attempts_to_pass(tries),
        retries(tries, played),
        response_by_day((r.created_at, r.processing_ms) for r in rows),
    )


# ---------- Markdown ----------
def _num(value: float | None) -> str:
    if value is None:
        return NO_DATA
    return str(value) if isinstance(value, int) else f"{value:.2f}"


def _table(columns: Sequence[str], rows: Sequence[Sequence[object]]) -> str:
    return to_markdown_table(columns, rows) if rows else NO_DATA


def render(r: PilotReport) -> str:
    s = r.first_success
    weekly = [(w.week.isoformat(), w.lines, w.learners) for w in r.weekly]
    first = (
        [(s.learners, s.passed_ever, s.passed_same_day, _num(s.same_day_share),
          _num(s.median_minutes))]
        if s.learners
        else []
    )  # fmt: skip
    gone = [
        ("неизвестен" if lesson is None else lesson, n)
        for lesson, n in sorted(r.drop_off.items(), key=lambda kv: (kv[0] is None, kv[0] or 0))
    ]
    effort = [
        (lesson, e.passed, _num(e.median_attempts), e.not_passed) for lesson, e in r.effort.items()
    ]
    retry = [
        (name, e.pairs, _num(e.mean_delta), _num(e.improved_share), e.named, e.fixed,
         _num(e.fixed_share))
        for name, e in r.retries.items()
        if e.pairs
    ]  # fmt: skip
    timing = [
        (d.day.isoformat(), d.attempts, _num(d.p50_ms), _num(d.p90_ms), _num(d.max_ms))
        for d in r.response
    ]
    return "\n".join(
        [
            "## Главная метрика пилота (G4, Q4.4)",
            "",
            "Строки книги, впервые засчитанные за календарную неделю (с понедельника, UTC): каждая "
            "строка — один раз на ученика. Зачёт — по вердикту бота тогда. Заглушка не входит.",
            "",
            _table(("неделя", "новых строк", "учеников"), weekly),
            "",
            "## Путь новичка (G4)",
            "",
            "Первый успех (Q4.1): засчитанная попытка в день регистрации и минуты до первого "
            "зачёта.",
            "",
            _table(
                ("учеников", "засчитано хоть раз", "в день регистрации", "доля", "медиана, мин"),
                first,
            ),
            "",
            f"Где бросают (Q4.3): урок последней попытки у тех, кто {IDLE_DAYS}+ дней не "
            "занимался.",
            "",
            _table(("урок", "ушло учеников"), gone),
            "",
            "Попыток до первого зачёта строки (Q4.5), по урокам:",
            "",
            _table(("урок", "строк засчитано", "медиана попыток", "не засчитано"), effort),
            "",
            "## Повтор после объяснения (G3, Q3.1–Q3.3)",
            "",
            "Пара — незасчитанная попытка и следующая попытка того же ученика по той же строке. "
            "«Исправлено» — названная ботом ошибка (позиция и звук) исчезла; при другом варианте "
            "эталона ошибки не сравниваются. «С эталоном» — между попытками прослушан 🔊. "
            "Это разведка (E-7), не причинный вывод.",
            "",
            _table(
                (
                    "группа",
                    "пар",
                    "Δ балла",
                    "доля с ростом",
                    "названо ошибок",
                    "исправлено",
                    "доля исправленных",
                ),
                retry,
            ),
            "",
            "## Время ответа по дням (G5, Q5.1)",
            "",
            _table(("день", "попыток", "p50, мс", "p90, мс", "максимум, мс"), timing),
            "",
        ]
    )

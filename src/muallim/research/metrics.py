"""Метрики GQM (docs/research/metrics-gqm.md): точность проверки, время ответа, сбои, возврат.

Формулы — чистые функции; ``collect`` берёт данные через SQLAlchemy Core, поэтому одинаково
работает на SQLite (тесты) и PostgreSQL. Попытки заглушки и метки ``audio_unusable`` /
``off_task`` не входят.
"""

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from uuid import UUID

from sqlalchemy import ColumnElement, select
from sqlalchemy.ext.asyncio import AsyncSession

from muallim.infrastructure.db.tables import (
    annotations,
    attempts,
    detected_errors,
    interaction_events,
)
from muallim.research.reports import to_markdown_table

STUB = "stub"
UNUSABLE = frozenset({"audio_unusable", "off_task"})
RETURN_DAYS = 7


# ---------- формулы ----------
@dataclass(frozen=True, slots=True)
class DetectionQuality:
    tp: int
    fp: int
    fn: int | None  # None — пропуски неизвестны (по типу ошибки)
    precision: float | None
    recall: float | None
    f1: float | None


def detection_quality(tp: int, fp: int, fn: int | None) -> DetectionQuality:
    """TP — подтверждённые ошибки, FP — ``false_alarm`` + ``wrong_error``, FN — ``missed_error``."""
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if fn is not None and tp + fn else None
    f1 = None
    if precision is not None and recall is not None:
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return DetectionQuality(tp, fp, fn, precision, recall, f1)


def teacher_passes(label: str, bot_passed: bool) -> bool | None:
    """Вердикт учителя «засчитать?», выведенный из метки на всю попытку; None — оценить нельзя."""
    if label == "correct":
        return bot_passed
    if label == "false_alarm":
        return True
    if label in ("missed_error", "wrong_error"):
        return False
    return None


def cohen_kappa(pairs: Sequence[tuple[bool, bool]]) -> float | None:
    """κ Коэна для двух оценщиков «засчитать / нет»; None — нет данных или нет разброса (pe = 1)."""
    if not pairs:
        return None
    n = len(pairs)
    observed = sum(a == b for a, b in pairs) / n
    first, second = sum(a for a, _ in pairs) / n, sum(b for _, b in pairs) / n
    expected = first * second + (1 - first) * (1 - second)
    return None if expected == 1 else (observed - expected) / (1 - expected)


def nearest_rank(values: Iterable[int], percent: int) -> int | None:
    """Процентиль методом ближайшего ранга: значение, не меньше которого ``percent`` % выборки."""
    ordered = sorted(values)
    if not ordered:
        return None
    rank = max(1, (percent * len(ordered) + 99) // 100)
    return ordered[rank - 1]


@dataclass(frozen=True, slots=True)
class Retention:
    learners: int
    returned: int  # занимался ещё хотя бы в один другой день
    cohort_7d: int  # первый день не позже чем 7 дней назад — только у них можно проверить возврат
    returned_7d: int  # занимался через 7 и более дней после первого дня


def retention(days: Mapping[str, set[date]], today: date) -> Retention:
    returned = cohort = returned_late = 0
    for active in days.values():
        first = min(active)
        returned += any(day > first for day in active)
        if first <= today - timedelta(days=RETURN_DAYS):
            cohort += 1
            returned_late += any(day >= first + timedelta(days=RETURN_DAYS) for day in active)
    return Retention(len(days), returned, cohort, returned_late)


# ---------- сбор из БД ----------
@dataclass(frozen=True, slots=True)
class VerdictAgreement:
    accepted: int  # бот засчитал
    false_accepts: int  # …а учитель — нет
    rejected: int  # бот не засчитал
    false_rejects: int  # …а учитель засчитал бы
    far: float | None
    frr: float | None


@dataclass(frozen=True, slots=True)
class ResponseTime:
    attempts: int
    p50_ms: int | None
    p90_ms: int | None
    max_ms: int | None


@dataclass(frozen=True, slots=True)
class Failures:
    failed: int
    assessed: int
    share: float | None
    by_stage: dict[str, int]


@dataclass(frozen=True, slots=True)
class Metrics:
    detection: DetectionQuality
    by_kind: dict[str, DetectionQuality]
    verdicts: VerdictAgreement
    kappa_bot_teacher: float | None
    pairs_bot_teacher: int
    kappa_teachers: float | None
    pairs_teachers: int
    response: ResponseTime
    failures: Failures
    retention: Retention


async def collect(session: AsyncSession, today: date) -> Metrics:
    real = attempts.c.model_version != STUB
    detection, by_kind = await _detection(session, real)
    pairs, teacher_pairs = await _verdict_pairs(session, real)
    accepted = [teacher for bot, teacher in pairs if bot]
    rejected = [teacher for bot, teacher in pairs if not bot]
    verdicts = VerdictAgreement(
        len(accepted), accepted.count(False), len(rejected), rejected.count(True),
        accepted.count(False) / len(accepted) if accepted else None,
        rejected.count(True) / len(rejected) if rejected else None,
    )  # fmt: skip

    rows = (
        await session.execute(
            select(attempts.c.learner_id, attempts.c.processing_ms, attempts.c.created_at).where(
                real
            )
        )
    ).all()
    times = [ms for _, ms, _ in rows]
    response = ResponseTime(
        len(times), nearest_rank(times, 50), nearest_rank(times, 90), max(times, default=None)
    )
    days: dict[str, set[date]] = defaultdict(set)
    for learner_id, _, created_at in rows:
        days[str(learner_id)].add(_day(created_at))

    return Metrics(
        detection, by_kind, verdicts,
        cohen_kappa(pairs), len(pairs), cohen_kappa(teacher_pairs), len(teacher_pairs),
        response, await _failures(session), retention(days, today),
    )  # fmt: skip


async def _detection(
    session: AsyncSession, real: ColumnElement[bool]
) -> tuple[DetectionQuality, dict[str, DetectionQuality]]:
    error_level = await session.execute(
        select(annotations.c.label, detected_errors.c.kind)
        .join(detected_errors, detected_errors.c.id == annotations.c.detected_error_id)
        .join(attempts, attempts.c.id == annotations.c.attempt_id)
        .where(real)
    )
    tp: Counter[str] = Counter()
    fp: Counter[str] = Counter()
    for label, kind in error_level.all():
        if label == "correct":
            tp[kind] += 1
        elif label in ("false_alarm", "wrong_error"):
            fp[kind] += 1
    missed = await session.execute(
        select(annotations.c.id)
        .join(attempts, attempts.c.id == annotations.c.attempt_id)
        .where(real, annotations.c.detected_error_id.is_(None))
        .where(annotations.c.label == "missed_error")
    )
    total = detection_quality(sum(tp.values()), sum(fp.values()), len(missed.all()))
    kinds = sorted(set(tp) | set(fp))
    return total, {k: detection_quality(tp[k], fp[k], None) for k in kinds}


async def _verdict_pairs(
    session: AsyncSession, real: ColumnElement[bool]
) -> tuple[list[tuple[bool, bool]], list[tuple[bool, bool]]]:
    """(бот, учитель) по каждой метке на попытку и (учитель 1, учитель 2) там, где их двое."""
    rows = await session.execute(
        select(
            annotations.c.attempt_id, annotations.c.annotator, annotations.c.label,
            annotations.c.created_at, attempts.c.verdict,
        )
        .join(attempts, attempts.c.id == annotations.c.attempt_id)
        .where(real, annotations.c.detected_error_id.is_(None))
        .order_by(annotations.c.created_at, annotations.c.annotator, annotations.c.id)
    )  # fmt: skip
    pairs: list[tuple[bool, bool]] = []
    by_attempt: dict[UUID, dict[str, bool]] = defaultdict(dict)
    for attempt_id, annotator, label, _, verdict in rows.all():
        if label in UNUSABLE:
            continue
        bot = verdict != "failed"
        teacher = teacher_passes(label, bot)
        if teacher is None:
            continue
        pairs.append((bot, teacher))
        by_attempt[attempt_id].setdefault(annotator, teacher)  # первая метка учителя
    teachers = [tuple(v.values())[:2] for v in by_attempt.values() if len(v) >= 2]
    return pairs, [(a, b) for a, b in teachers]


async def _failures(session: AsyncSession) -> Failures:
    rows = await session.execute(
        select(interaction_events.c.event, interaction_events.c.payload).where(
            interaction_events.c.event.in_(("attempt_assessed", "recognition_failed"))
        )
    )
    assessed, stages = 0, Counter[str]()
    for event, payload in rows.all():
        if event == "attempt_assessed":
            assessed += 1
        else:
            stages[str((payload or {}).get("stage", "unknown"))] += 1
    failed = sum(stages.values())
    total = failed + assessed
    return Failures(failed, assessed, failed / total if total else None, dict(stages))


def _day(moment: datetime) -> date:
    return moment.date()


# ---------- Markdown ----------
def render(m: Metrics) -> str:
    d, v, t, f, r = m.detection, m.verdicts, m.response, m.failures, m.retention
    quality = [
        ("precision", _num(d.precision), f"TP {d.tp}, FP {d.fp}"),
        ("recall", _num(d.recall), f"TP {d.tp}, FN {d.fn}"),
        ("F1", _num(d.f1), ""),
        ("FAR (засчитано ошибочное)", _num(v.far), f"{v.false_accepts} из {v.accepted}"),
        ("FRR (не засчитано верное)", _num(v.frr), f"{v.false_rejects} из {v.rejected}"),
        ("κ бот — учитель", _num(m.kappa_bot_teacher), f"пар: {m.pairs_bot_teacher}"),
        ("κ учитель — учитель", _num(m.kappa_teachers), f"пар: {m.pairs_teachers}"),
    ]
    kinds = [(kind, q.tp, q.fp, _num(q.precision)) for kind, q in m.by_kind.items()]
    timing = [(t.attempts, _num(t.p50_ms), _num(t.p90_ms), _num(t.max_ms))] if t.attempts else []
    stages = ", ".join(f"{s}: {n}" for s, n in sorted(f.by_stage.items()))
    failures = [(f.failed, f.assessed, _num(f.share), stages)] if f.failed + f.assessed else []
    returns = [(r.learners, r.returned, r.cohort_7d, r.returned_7d)] if r.learners else []
    days = RETURN_DAYS
    return "\n".join(
        [
            "## Точность проверки (G1, RQ-1)",
            "",
            "Формулы и цели — `docs/research/metrics-gqm.md`. "
            "Заглушка, `audio_unusable` и `off_task` не входят.",
            "",
            to_markdown_table(("метрика", "значение", "из чего"), quality),
            "",
            "Precision по типу ошибки (пропуски по типу неизвестны):",
            "",
            to_markdown_table(("тип", "TP", "FP", "precision"), kinds),
            "",
            "## Время ответа (G5, QAS-03)",
            "",
            "`processing_ms` — распознавание и оценка, без загрузки из Telegram и отрисовки.",
            "",
            to_markdown_table(("попыток", "p50, мс", "p90, мс", "максимум, мс"), timing),
            "",
            "## Сбои распознавания (G5, QAS-04)",
            "",
            "«Оценено» — события `attempt_assessed`: в них нет версии модели, поэтому сюда "
            "входят и попытки заглушки времён разработки. В пилоте — только модель (FR-42).",
            "",
            to_markdown_table(("сбоев", "оценено", "доля сбоев", "по этапам"), failures),
            "",
            "## Возврат учеников (G4)",
            "",
            f"Через {days} дней — только у тех, кто начал не позже чем {days} дней назад.",
            "",
            to_markdown_table(
                (
                    "учеников",
                    "вернулись в другой день",
                    f"в когорте {days} дн.",
                    f"вернулись через ≥ {days} дн.",
                ),
                returns,
            ),
            "",
        ]
    )


def _num(value: float | None) -> str:
    if value is None:
        return "нет данных"
    return str(value) if isinstance(value, int) else f"{value:.3f}"

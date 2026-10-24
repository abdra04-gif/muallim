"""Метрики GQM (docs/research/metrics-gqm.md): точность проверки, время ответа, сбои, возврат.

Точность проверки — по каждой фонеме эталона, по схеме MDD (TA/FR/FA/TR, SRC-064), как в
L2-ARCTIC (SRC-063) и Iqra'Eval (SRC-043): разметчик пишет, что прозвучало на самом деле,
модель — что услышала; оба сравниваются с эталоном. Каждый разметчик — отдельный «эталон
учителя»; берётся его последняя метка на попытку. Формулы — чистые функции; ``collect`` берёт
данные через SQLAlchemy Core (SQLite в тестах, PostgreSQL в работе). Заглушка и метки
``audio_unusable`` / ``off_task`` не входят.

95 % ДИ (FR-55, preregistration.md H1.2–H1.4) — кластерный бутстрэп по ученикам: попытки одного
ученика зависимы, поэтому выборка повторяется целыми учениками (``cluster_bootstrap``).
"""

import math
import random
from collections import Counter, defaultdict
from collections.abc import Callable, Hashable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, select
from sqlalchemy.ext.asyncio import AsyncSession

from muallim.domain.assessment import ErrorKind, assess
from muallim.domain.policy import GradingPolicy, Verdict
from muallim.infrastructure.db.tables import annotations, attempts, interaction_events
from muallim.research.reports import to_markdown_table

STUB = "stub"
AGREE, FIX = "agree", "fix"  # разметчик согласен с ботом / исправил, что прозвучало
USABLE = frozenset({AGREE, FIX})  # попытку можно оценить
UNUSABLE = frozenset({"audio_unusable", "off_task"})
STATUSES = USABLE | UNUSABLE  # метки руководства 2.x; старые (1.0, без фонем) в метрики не входят
RETURN_DAYS = 7
# Версия правила сравнения по фонемам (phoneme_errors / phoneme_outcomes). Менять вместе с
# правилом: выгрузка «по звукам» её пишет, чтобы итоги разных версий не смешивались.
COMPARISON_VERSION = "1"
BOOTSTRAP_REPS = 2000  # повторов бутстрэпа: обычный выбор для 95 % процентильного ДИ
CI_LEVEL = 0.95


# ---------- формулы: по фонемам ----------
@dataclass(frozen=True, slots=True)
class PhonemeCounts:
    """TA — верно и принято, FR — верно, но забраковано (ложная тревога), FA — ошибка
    пропущена, TR — ошибка найдена; ``correct_diagnosis`` — среди TR модель услышала то же,
    что разметчик."""

    ta: int = 0
    fr: int = 0
    fa: int = 0
    tr: int = 0
    correct_diagnosis: int = 0

    def __add__(self, other: "PhonemeCounts") -> "PhonemeCounts":
        return PhonemeCounts(
            self.ta + other.ta, self.fr + other.fr, self.fa + other.fa, self.tr + other.tr,
            self.correct_diagnosis + other.correct_diagnosis,
        )  # fmt: skip


def phoneme_errors(reference: str, heard: str) -> dict[int, tuple[ErrorKind, str]]:
    """Позиции эталона с ошибкой → (тип, что прозвучало). Те же правила, что у бота
    (``domain.assessment``: калькаля при остановке — не ошибка). Замена нескольких звуков
    отмечает каждую фонему; вставка относится к фонеме, перед которой вставлено (в конце строки
    — к последней)."""
    marks: dict[int, tuple[ErrorKind, str]] = {}
    last = max(len(reference) - 1, 0)
    for error in assess(reference, heard).errors:
        for k in range(max(len(error.expected), 1)):
            marks.setdefault(min(error.position + k, last), (error.kind, error.heard))
    return marks


class Outcome(StrEnum):
    """Итог по фонеме — схема MDD (SRC-064); значения пишутся в phonemes.csv."""

    CORRECT_ACCEPT = "correct_accept"  # TA: прочитано верно, модель приняла
    FALSE_REJECTION = "false_rejection"  # FR: прочитано верно, модель забраковала (ложная тревога)
    FALSE_ACCEPT = "false_accept"  # FA: ошибка, модель её пропустила
    TRUE_REJECTION = "true_rejection"  # TR: ошибка, модель её нашла


@dataclass(frozen=True, slots=True)
class PhonemeOutcome:
    """Одна фонема эталона: что ждали, что услышала модель, что — разметчик, и итог.
    ``same_diagnosis`` — только для TR: модель услышала то же, что разметчик."""

    position: int
    expected: str
    model_heard: str
    human_heard: str
    outcome: Outcome
    same_diagnosis: bool | None
    model_kind: ErrorKind | None
    human_kind: ErrorKind | None


def _heard_at(reference: str, heard: str) -> list[str]:
    """Что прозвучало на месте каждой фонемы эталона — для показа (итоги считает
    ``phoneme_errors``). Вставка — перед фонемой, в конце строки — после последней; несколько
    вставок у одной фонемы видны все. Замена нескольких звуков — весь фрагмент у каждой фонемы."""
    before, after = [""] * len(reference), [""] * len(reference)
    core = list(reference)
    replaced: set[int] = set()
    for error in assess(reference, heard).errors:
        if error.expected:
            for pos in range(error.position, error.position + len(error.expected)):
                if pos not in replaced:
                    core[pos] = error.heard
                    replaced.add(pos)
        elif error.position < len(reference):
            before[error.position] += error.heard
        elif reference:
            after[-1] += error.heard
    return [b + c + a for b, c, a in zip(before, core, after, strict=True)]


def phoneme_outcomes(reference: str, model: str, human: str) -> tuple[PhonemeOutcome, ...]:
    """Сравнение по каждой фонеме эталона: где и как модель права или ошиблась."""
    by_model, by_human = phoneme_errors(reference, model), phoneme_errors(reference, human)
    model_heard, human_heard = _heard_at(reference, model), _heard_at(reference, human)
    rows = []
    for pos in range(len(reference)):
        m, h = by_model.get(pos), by_human.get(pos)
        if m and h:
            outcome = Outcome.TRUE_REJECTION
        elif m:
            outcome = Outcome.FALSE_REJECTION
        elif h:
            outcome = Outcome.FALSE_ACCEPT
        else:
            outcome = Outcome.CORRECT_ACCEPT
        rows.append(
            PhonemeOutcome(
                position=pos,
                expected=reference[pos],
                model_heard=model_heard[pos],
                human_heard=human_heard[pos],
                outcome=outcome,
                same_diagnosis=m[1] == h[1] if m and h else None,
                model_kind=m[0] if m else None,
                human_kind=h[0] if h else None,
            )
        )
    return tuple(rows)


def phoneme_decisions(reference: str, model: str, human: str) -> PhonemeCounts:
    """Сумма по фонемам — из того же разбора, что файл «по звукам» (не могут разойтись)."""
    rows = phoneme_outcomes(reference, model, human)
    count = Counter(r.outcome for r in rows)
    return PhonemeCounts(
        count[Outcome.CORRECT_ACCEPT], count[Outcome.FALSE_REJECTION],
        count[Outcome.FALSE_ACCEPT], count[Outcome.TRUE_REJECTION],
        sum(r.same_diagnosis is True for r in rows),
    )  # fmt: skip


@dataclass(frozen=True, slots=True)
class MddQuality:
    precision: float | None  # TR / (TR + FR): из найденных моделью ошибок — настоящие
    recall: float | None  # TR / (TR + FA): из настоящих ошибок — найдены
    f1: float | None
    far: float | None  # FA / (FA + TR): ошибка пропущена — ученик думает, что прочитал верно
    frr: float | None  # FR / (TA + FR): верное забраковано — новичок теряет мотивацию
    diagnosis: float | None  # среди найденных ошибок — модель услышала то же, что учитель


def _ratio(part: int, whole: int) -> float | None:
    return part / whole if whole else None


def mdd_quality(c: PhonemeCounts) -> MddQuality:
    precision, recall = _ratio(c.tr, c.tr + c.fr), _ratio(c.tr, c.tr + c.fa)
    f1 = None
    if precision is not None and recall is not None:
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return MddQuality(
        precision, recall, f1, _ratio(c.fa, c.fa + c.tr), _ratio(c.fr, c.ta + c.fr),
        _ratio(c.correct_diagnosis, c.tr),
    )  # fmt: skip


@dataclass(frozen=True, slots=True)
class KindQuality:
    """По типу ошибки: precision — по типу, который назвала модель; recall — по типу ошибки,
    которую записал разметчик (пропущенную ошибку модель никак не назвала)."""

    flagged: int  # фонем, отмеченных моделью этим типом
    confirmed: int  # …и разметчик тоже слышит там ошибку
    errors: int  # фонем с ошибкой этого типа по разметке
    caught: int  # …и модель там тоже отметила ошибку

    @property
    def precision(self) -> float | None:
        return _ratio(self.confirmed, self.flagged)

    @property
    def recall(self) -> float | None:
        return _ratio(self.caught, self.errors)


def krippendorff_alpha_nominal(units: Sequence[Sequence[Hashable | None]]) -> float | None:
    """α Криппендорфа для номинальной шкалы (SRC-065).

    ``units`` — по строке на единицу, в ней значения оценщиков, None — не оценивал. Единицы с одной
    оценкой не входят. None — нет пар или нет разброса значений.
    """
    totals: Counter[Hashable] = Counter()
    disagree = 0.0
    for unit in units:
        values = Counter(v for v in unit if v is not None)
        m = sum(values.values())
        if m < 2:
            continue
        totals.update(values)
        disagree += (m * m - sum(n * n for n in values.values())) / (m - 1)
    n = sum(totals.values())
    expected = n * n - sum(c * c for c in totals.values())
    if not n or not expected:
        return None
    return 1 - (n - 1) * disagree / expected


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


def cluster_bootstrap[T](
    clusters: Sequence[Sequence[T]],
    stat: Callable[[Sequence[T]], float | None],
    *,
    reps: int = BOOTSTRAP_REPS,
    level: float = CI_LEVEL,
    seed: int = 0,
) -> tuple[float, float] | None:
    """Процентильный ДИ статистики, выборка — целыми кластерами (учениками) с возвращением.

    Повтор, где статистика не определена (None), пропускается. None — меньше двух кластеров или
    ни один повтор не дал значения. ``seed`` постоянный: отчёт воспроизводим.
    """
    if not 0 < level < 1:
        msg = f"level — доля строго между 0 и 1, а не {level}"
        raise ValueError(msg)
    if len(clusters) < 2:  # из одного ученика повторять нечего
        return None
    rng = random.Random(seed)  # noqa: S311 — не криптография, нужна воспроизводимость
    values: list[float] = []
    for _ in range(reps):
        sample = [v for c in rng.choices(clusters, k=len(clusters)) for v in c]
        if (value := stat(sample)) is not None:
            values.append(value)
    if not values:
        return None
    values.sort()
    tail = (1 - level) / 2
    low = values[min(len(values) - 1, math.floor(tail * len(values)))]
    high = values[max(0, math.ceil((1 - tail) * len(values)) - 1)]
    return low, high


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


@dataclass(frozen=True, slots=True)
class ReviewCounts:
    """Сколько раз разметчик согласился с ботом и сколько исправил — отдельно по вердикту бота."""

    agree_passed: int = 0  # бот засчитал, разметчик согласен
    fix_passed: int = 0  # бот засчитал, разметчик исправил
    agree_failed: int = 0  # бот не засчитал, разметчик согласен
    fix_failed: int = 0  # бот не засчитал, разметчик исправил
    unusable: int = 0  # оценить нельзя: шум или прочитано не то

    @property
    def agree(self) -> int:
        return self.agree_passed + self.agree_failed

    @property
    def fix(self) -> int:
        return self.fix_passed + self.fix_failed

    @property
    def agreement(self) -> float | None:
        return _ratio(self.agree, self.agree + self.fix)


def _review(labels: Iterable[tuple[str, str, bool]]) -> dict[str, ReviewCounts]:
    """(разметчик, метка, бот засчитал) → счёт по разметчику; «все» — сумма."""
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    for annotator, status, passed in labels:
        key = "unusable" if status in UNUSABLE else f"{status}_{'passed' if passed else 'failed'}"
        counts[annotator][key] += 1
        counts["все"][key] += 1
    return {name: ReviewCounts(**c) for name, c in sorted(counts.items())}


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
class SelfCorrection:
    """Попытки, где ученик ошибся и тут же сам перечитал верно (руководство 2.1, ADR-0044).

    Отдельно от главных цифр RQ-1: достаточно отметки одного разметчика — попытка целиком здесь.
    """

    attempts: int
    phonemes: PhonemeCounts
    quality: MddQuality


@dataclass(frozen=True, slots=True)
class Metrics:
    phonemes: PhonemeCounts
    quality: MddQuality
    by_kind: dict[str, KindQuality]
    verdicts: VerdictAgreement
    kappa_bot_teacher: float | None
    pairs_bot_teacher: int
    kappa_teachers: float | None
    pairs_teachers: int
    alpha_phonemes: float | None  # согласие разметчиков «ошибка / верно» по каждой фонеме
    alpha_units: int
    review: dict[str, ReviewCounts]  # согласие разметчиков с ботом; ключ «все» — сумма
    annotated_attempts: int
    double_annotated: int
    response: ResponseTime
    failures: Failures
    retention: Retention
    self_corrected: SelfCorrection
    ci: dict[str, tuple[float, float] | None]  # 95 % ДИ бутстрэпом по ученикам
    by_sound: dict[str, KindQuality]  # Q1.5: по звуку эталона


@dataclass(frozen=True, slots=True)
class _Unit:
    """Вклад одной метки (или пары разметчиков) в метрики — для бутстрэпа по ученикам."""

    counts: PhonemeCounts | None = None
    verdict: tuple[bool, bool] | None = None  # (бот засчитал, учитель засчитал бы)
    teachers: tuple[bool, bool] | None = None  # вердикты двух разметчиков на одну попытку


def _units_counts(units: Sequence[_Unit]) -> PhonemeCounts:
    total = PhonemeCounts()
    for u in units:
        if u.counts is not None:
            total += u.counts
    return total


def _verdict_rate(units: Sequence[_Unit], *, bot: bool) -> float | None:
    """FAR вердикта (bot=True: засчитано, учитель — нет) или FRR (bot=False: наоборот)."""
    teacher = [t for b, t in (u.verdict for u in units if u.verdict) if b is bot]
    return _ratio(teacher.count(not bot), len(teacher))


def _count_sounds(
    by_sound: Mapping[str, Counter[str]], reference: str, model: set[int], human: set[int]
) -> None:
    """Q1.5: те же счёты, что по типу ошибки, но ключ — звук эталона на этой позиции."""
    for pos in model:
        by_sound["flagged"][reference[pos]] += 1
        by_sound["confirmed"][reference[pos]] += pos in human
    for pos in human:
        by_sound["errors"][reference[pos]] += 1
        by_sound["caught"][reference[pos]] += pos in model


_CI_STATS: dict[str, Callable[[Sequence[_Unit]], float | None]] = {
    "precision": lambda u: mdd_quality(_units_counts(u)).precision,
    "recall": lambda u: mdd_quality(_units_counts(u)).recall,
    "F1": lambda u: mdd_quality(_units_counts(u)).f1,
    "FAR вердикта": lambda u: _verdict_rate(u, bot=True),
    "FRR вердикта": lambda u: _verdict_rate(u, bot=False),
    "κ бот — учитель": lambda u: cohen_kappa([x.verdict for x in u if x.verdict]),
    "κ учитель — учитель": lambda u: cohen_kappa([x.teachers for x in u if x.teachers]),
}


@dataclass(frozen=True, slots=True)
class _Label:
    learner: UUID
    status: str
    actual: str | None
    reference: str
    heard: str
    bot_passed: bool
    policy: GradingPolicy
    self_corrected: bool


async def collect(session: AsyncSession, today: date) -> Metrics:
    real = attempts.c.model_version != STUB
    labels = await _latest_labels(session, real)
    counts = PhonemeCounts()
    flagged, confirmed, errors, caught = (
        Counter[str](),
        Counter[str](),
        Counter[str](),
        Counter[str](),
    )
    by_sound = {name: Counter[str]() for name in ("flagged", "confirmed", "errors", "caught")}
    clusters: dict[UUID, list[_Unit]] = defaultdict(list)
    pairs: list[tuple[bool, bool]] = []
    usable: dict[UUID, dict[str, tuple[bool, frozenset[int], int]]] = defaultdict(dict)
    self_marked = {attempt_id for (attempt_id, _), lab in labels.items() if lab.self_corrected}
    self_counts = PhonemeCounts()
    learner_of: dict[UUID, UUID] = {}
    for (attempt_id, annotator), lab in sorted(labels.items(), key=lambda kv: kv[0][1]):
        if lab.status not in USABLE or lab.actual is None:
            continue
        if attempt_id in self_marked:  # самоисправление — отдельный блок, не в главных цифрах
            self_counts += phoneme_decisions(lab.reference, lab.heard, lab.actual)
            continue
        decided = phoneme_decisions(lab.reference, lab.heard, lab.actual)
        counts += decided
        by_model = phoneme_errors(lab.reference, lab.heard)
        by_human = phoneme_errors(lab.reference, lab.actual)
        for pos, (kind, _) in by_model.items():
            flagged[kind] += 1
            confirmed[kind] += pos in by_human
        for pos, (kind, _) in by_human.items():
            errors[kind] += 1
            caught[kind] += pos in by_model
        _count_sounds(by_sound, lab.reference, set(by_model), set(by_human))
        teacher = lab.policy.verdict(assess(lab.reference, lab.actual)) != Verdict.FAILED
        pairs.append((lab.bot_passed, teacher))
        clusters[lab.learner].append(_Unit(decided, (lab.bot_passed, teacher)))
        learner_of[attempt_id] = lab.learner
        usable[attempt_id][annotator] = (teacher, frozenset(by_human), len(lab.reference))

    accepted = [teacher for bot, teacher in pairs if bot]
    rejected = [teacher for bot, teacher in pairs if not bot]
    verdicts = VerdictAgreement(
        len(accepted), accepted.count(False), len(rejected), rejected.count(True),
        _ratio(accepted.count(False), len(accepted)), _ratio(rejected.count(True), len(rejected)),
    )  # fmt: skip
    shared_by = {a: list(v.values()) for a, v in usable.items() if len(v) >= 2}
    shared = list(shared_by.values())
    teacher_pairs = [(a[0], b[0]) for a, b, *_ in shared]  # первые два по коду разметчика
    for attempt_id, (first, second, *_) in shared_by.items():
        clusters[learner_of[attempt_id]].append(_Unit(teachers=(first[0], second[0])))
    groups = list(clusters.values())
    ci = {name: cluster_bootstrap(groups, stat) for name, stat in _CI_STATS.items()}
    sounds = sorted(set(by_sound["flagged"]) | set(by_sound["errors"]))
    units = [
        ["err" if pos in marks else "ok" for _, marks, _ in raters]
        for raters in shared
        for pos in range(raters[0][2])
    ]
    per_attempt = Counter(attempt_id for attempt_id, _ in labels)
    kinds = sorted(set(flagged) | set(errors))

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
        counts, mdd_quality(counts),
        {k: KindQuality(flagged[k], confirmed[k], errors[k], caught[k]) for k in kinds},
        verdicts, cohen_kappa(pairs), len(pairs), cohen_kappa(teacher_pairs), len(teacher_pairs),
        krippendorff_alpha_nominal(units), len(units),
        _review((annotator, lab.status, lab.bot_passed) for (_, annotator), lab in labels.items()),
        len(per_attempt), sum(1 for n in per_attempt.values() if n >= 2),
        response, await _failures(session), retention(days, today),
        SelfCorrection(len(self_marked), self_counts, mdd_quality(self_counts)),
        ci,
        {
            sound: KindQuality(*(by_sound[n][sound] for n in ("flagged", "confirmed", "errors",
                                                               "caught")))
            for sound in sounds
        },
    )  # fmt: skip


async def _latest_labels(
    session: AsyncSession, real: ColumnElement[bool]
) -> dict[tuple[UUID, str], _Label]:
    """Последняя метка каждого разметчика на каждую попытку (раньше поставленные — история)."""
    rows = await session.execute(
        select(
            attempts.c.learner_id, annotations.c.attempt_id, annotations.c.annotator,
            annotations.c.label,
            annotations.c.corrected_phonemes, attempts.c.reference_phonemes,
            attempts.c.heard_phonemes, attempts.c.verdict, attempts.c.policy,
            annotations.c.self_corrected,
        )
        .join(attempts, attempts.c.id == annotations.c.attempt_id)
        .where(real, annotations.c.label.in_(STATUSES))
        .order_by(annotations.c.created_at, annotations.c.id)
    )  # fmt: skip
    latest: dict[tuple[UUID, str], _Label] = {}
    for (
        learner,
        attempt_id,
        annotator,
        status,
        actual,
        reference,
        heard,
        verdict,
        policy,
        own,
    ) in rows.all():
        latest[(attempt_id, annotator)] = _Label(
            learner, status, actual, reference, heard, verdict != Verdict.FAILED, _policy(policy),
            bool(own),
        )  # fmt: skip
    return latest


def _policy(stored: Mapping[str, Any] | None) -> GradingPolicy:
    """Пороги, с которыми попытку оценил бот (ADR-0019); у старых попыток — по умолчанию."""
    if not stored:
        return GradingPolicy()
    return GradingPolicy(int(stored["pass_threshold"]), int(stored["excellent_threshold"]))


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
REVIEW_COLUMNS = (
    "разметчик", "согласен: засчитано", "исправил: засчитано", "согласен: не засчитано",
    "исправил: не засчитано", "нельзя оценить", "доля согласия",
)  # fmt: skip
KIND_COLUMNS = (
    "тип", "отметила модель", "подтверждено", "precision", "ошибок по разметке", "нашла модель",
    "recall",
)  # fmt: skip


def render(m: Metrics) -> str:
    q, c, v, t, f, r = m.quality, m.phonemes, m.verdicts, m.response, m.failures, m.retention
    sc, sq = m.self_corrected.phonemes, m.self_corrected.quality
    own = [
        ("precision", _num(sq.precision), f"TR {sc.tr}, FR {sc.fr}"),
        ("recall", _num(sq.recall), f"TR {sc.tr}, FA {sc.fa}"),
        ("F1", _num(sq.f1), ""),
    ]
    quality = [
        ("precision", _num(q.precision), f"TR {c.tr}, FR {c.fr}"),
        ("recall", _num(q.recall), f"TR {c.tr}, FA {c.fa}"),
        ("F1", _num(q.f1), ""),
        ("FAR по фонемам (ошибка пропущена)", _num(q.far), f"FA {c.fa} из {c.fa + c.tr}"),
        ("FRR по фонемам (верное забраковано)", _num(q.frr), f"FR {c.fr} из {c.ta + c.fr}"),
        ("верный диагноз", _num(q.diagnosis), f"{c.correct_diagnosis} из {c.tr}"),
        ("FAR вердикта (засчитано ошибочное)", _num(v.far), f"{v.false_accepts} из {v.accepted}"),
        ("FRR вердикта (не засчитано верное)", _num(v.frr), f"{v.false_rejects} из {v.rejected}"),
        ("κ бот — учитель (вердикт)", _num(m.kappa_bot_teacher), f"пар: {m.pairs_bot_teacher}"),
        ("κ учитель — учитель (вердикт)", _num(m.kappa_teachers), f"пар: {m.pairs_teachers}"),
        ("α учитель — учитель (фонемы)", _num(m.alpha_phonemes), f"фонем: {m.alpha_units}"),
    ]
    intervals = [(name, _interval(value)) for name, value in m.ci.items()]
    sounds = [
        (sound, k.flagged, k.confirmed, _num(k.precision), k.errors, k.caught, _num(k.recall))
        for sound, k in m.by_sound.items()
    ]
    kinds = [
        (kind, k.flagged, k.confirmed, _num(k.precision), k.errors, k.caught, _num(k.recall))
        for kind, k in m.by_kind.items()
    ]
    review = [
        (name, k.agree_passed, k.fix_passed, k.agree_failed, k.fix_failed, k.unusable,
         _num(k.agreement))
        for name, k in m.review.items()
    ]  # fmt: skip
    timing = [(t.attempts, _num(t.p50_ms), _num(t.p90_ms), _num(t.max_ms))] if t.attempts else []
    stages = ", ".join(f"{s}: {n}" for s, n in sorted(f.by_stage.items()))
    failures = [(f.failed, f.assessed, _num(f.share), stages)] if f.failed + f.assessed else []
    returns = [(r.learners, r.returned, r.cohort_7d, r.returned_7d)] if r.learners else []
    days = RETURN_DAYS
    return "\n".join(
        [
            "## Точность проверки (G1, RQ-1)",
            "",
            "Формулы и цели — `docs/research/metrics-gqm.md`. По каждой фонеме эталона: что "
            "услышала модель и что записал разметчик (схема MDD, как в L2-ARCTIC и Iqra'Eval). "
            "Заглушка, `audio_unusable` и `off_task` не входят.",
            "",
            f"Размечено попыток: {m.annotated_attempts}, из них двумя и более разметчиками: "
            f"{m.double_annotated}. Фонем: TA {c.ta}, FR {c.fr}, FA {c.fa}, TR {c.tr}.",
            "",
            to_markdown_table(("метрика", "значение", "из чего"), quality),
            "",
            f"95 % ДИ — кластерный бутстрэп по ученикам ({BOOTSTRAP_REPS} повторов, "
            "процентильный): попытки одного ученика зависимы, поэтому выборка повторяется "
            "целыми учениками (`docs/research/preregistration.md`, H1.2–H1.4). Меньше двух "
            "учеников — нет данных.",
            "",
            to_markdown_table(("метрика", "95 % ДИ"), intervals),
            "",
            "По звуку эталона (Q1.5; precision — где отметила модель, recall — по разметке):",
            "",
            to_markdown_table(("звук", *KIND_COLUMNS[1:]), sounds),
            "",
            "## Самоисправления (руководство 2.1)",
            "",
            "Ученик ошибся и тут же сам перечитал верно — в одном голосовом. Такие попытки не "
            "входят в цифры выше (ADR-0044); хватает отметки одного разметчика.",
            "",
            f"Попыток: {m.self_corrected.attempts}. Фонем: TA {sc.ta}, FR {sc.fr}, FA {sc.fa}, "
            f"TR {sc.tr}.",
            "",
            to_markdown_table(("метрика", "значение", "из чего"), own),
            "",
            "## Согласие разметчиков с ботом",
            "",
            "Последняя метка каждого разметчика на попытку: `agree` — бот услышал верно, `fix` — "
            "разметчик исправил. Разметчик видит ответ бота — согласие может быть завышено "
            "подсказкой (`docs/research/preregistration.md`, §5).",
            "",
            to_markdown_table(REVIEW_COLUMNS, review),
            "",
            "По типу ошибки (precision — по типу, названному моделью; recall — по разметке):",
            "",
            to_markdown_table(KIND_COLUMNS, kinds),
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


def _interval(value: tuple[float, float] | None) -> str:
    return "нет данных" if value is None else f"{value[0]:.3f} – {value[1]:.3f}"


def _num(value: float | None) -> str:
    if value is None:
        return "нет данных"
    return str(value) if isinstance(value, int) else f"{value:.3f}"

"""Тестовые реализации портов: в памяти, детерминированные."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, fields, replace
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import UUID

from muallim.application.ports.erasures import ErasureAction
from muallim.application.ports.recognition import Recognition, RecognitionError, SuraRecognition
from muallim.domain.annotation import AnnotationTask, Label, next_annotator_code
from muallim.domain.assessment import Assessment, PronunciationError
from muallim.domain.attempt import Attempt
from muallim.domain.learner import ConsentRecord, Learner, LearnerProfile
from muallim.domain.policy import Verdict, is_mastered_verdict
from muallim.domain.report import LearnerReport
from muallim.domain.settings import DEFAULT_UTC_OFFSET_MIN, local_date
from muallim.domain.sura import AyahReference, SuraMode, SuraReading

if TYPE_CHECKING:
    from muallim.application.ports.recognition import Listening
    from muallim.application.ports.storage import Video
    from muallim.domain import review
    from muallim.domain.annotation import CellMark
    from muallim.domain.quiz import QuizAnswer


class FixedClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)

    def now(self) -> datetime:
        self.current += timedelta(seconds=1)
        return self.current


class SequentialIds:
    def __init__(self) -> None:
        self.n = 0

    def new_id(self) -> UUID:
        self.n += 1
        return UUID(int=self.n)


@dataclass
class InMemoryLearners:
    by_tg: dict[int, Learner] = field(default_factory=dict)
    consents: list[ConsentRecord] = field(default_factory=list)
    cascade_to: "InMemoryAttempts | None" = None  # как ON DELETE CASCADE в БД

    async def get_by_telegram_id(self, telegram_user_id: int) -> Learner | None:
        return self.by_tg.get(telegram_user_id)

    async def add(self, learner: Learner) -> None:
        self.by_tg[learner.telegram_user_id] = learner

    async def save(self, learner: Learner) -> None:
        self.by_tg[learner.telegram_user_id] = learner

    async def add_consent(self, record: ConsentRecord) -> None:
        self.consents.append(record)

    async def delete(self, learner_id: UUID) -> None:
        self.by_tg = {k: v for k, v in self.by_tg.items() if v.id != learner_id}
        self.consents = [c for c in self.consents if c.learner_id != learner_id]
        if self.cascade_to is not None:
            self.cascade_to.items = [
                (a, f) for a, f in self.cascade_to.items if a.learner_id != learner_id
            ]


@dataclass
class InMemoryProfiles:
    """Анкета ученика (FR-44, FR-65): одна на ученика, дополняется по одному ответу."""

    by_learner: dict[UUID, LearnerProfile] = field(default_factory=dict)

    async def get(self, learner_id: UUID) -> LearnerProfile | None:
        return self.by_learner.get(learner_id)

    async def save(self, profile: LearnerProfile) -> None:
        self.by_learner[profile.learner_id] = profile


@dataclass
class InMemoryAttempts:
    items: list[tuple[Attempt, tuple[str, ...]]] = field(default_factory=list)
    reports: list[LearnerReport] = field(default_factory=list)
    suras: "InMemorySuraReadings | None" = None  # сура, сданная целиком по тексту, — зачёт строк

    async def owner(self, attempt_id: UUID) -> UUID | None:
        return next((a.learner_id for a, _ in self.items if a.id == attempt_id), None)

    async def add_report(self, report: LearnerReport) -> bool:
        seen = {(r.attempt_id, r.learner_id) for r in self.reports}
        if (report.attempt_id, report.learner_id) in seen:
            return False
        self.reports.append(report)
        return True

    async def add(self, attempt: Attempt, feedback: tuple[str, ...]) -> None:
        # как в БД: у каждой ошибки — свой текст (detected_errors, zip strict)
        assert len(feedback) == len(attempt.assessment.errors)
        self.items.append((attempt, feedback))

    async def last_assessment(self, learner_id: UUID, item_id: str) -> Assessment | None:
        """Оценка последней попытки этой карточки для «было → стало»; «ещё раз» (балл 0, без
        разбора) пропускается — с ним не сравнивают (FR-70, решение автора 2026-11-20)."""
        return next(
            (
                a.assessment
                for a, _ in reversed(self.items)
                if a.learner_id == learner_id
                and a.item_id == item_id
                and a.verdict is not Verdict.AGAIN
            ),
            None,
        )

    async def last_verdict(self, learner_id: UUID, item_id: str) -> Verdict | None:
        """Вердикт последней попытки этой карточки — для «ещё раз не больше раза подряд»
        (FR-70 п. 6, ADR-0088 п. 6); None — первая попытка. «Не расслышано»
        (``model_output["unheard"]``) — не попытка: пропускается (решение автора 2026-11-20)."""
        return next(
            (
                a.verdict
                for a, _ in reversed(self.items)
                if a.learner_id == learner_id
                and a.item_id == item_id
                and a.model_output.get("unheard") is not True
            ),
            None,
        )

    async def mastered(self, learner_id: UUID) -> frozenset[str]:
        """Освоенные карточки — по вердикту (ADR-0088 п. 7): хоть одна попытка «отлично» или
        «засчитано»; карточки суры, сданной целиком по тексту, — тоже (FR-58)."""
        done = {
            a.item_id
            for a, _ in self.items
            if a.learner_id == learner_id and is_mastered_verdict(a.verdict)
        }
        if self.suras is not None:
            done |= await self.suras.credited(learner_id)
        return frozenset(done)

    async def best_scores(self, learner_id: UUID) -> Mapping[str, int]:
        best: dict[str, int] = {}
        for a, _ in self.items:
            if a.learner_id == learner_id:
                best[a.item_id] = max(best.get(a.item_id, 0), a.assessment.score)
        if self.suras is not None:
            for item_id in await self.suras.credited(learner_id):
                best[item_id] = 100
        return best

    async def count(self, learner_id: UUID) -> int:
        return sum(1 for a, _ in self.items if a.learner_id == learner_id)

    async def audio_hashes(self, learner_id: UUID) -> list[str]:
        return [
            a.audio_sha256 for a, _ in self.items if a.learner_id == learner_id and a.audio_sha256
        ]

    async def forget_audio(self, learner_id: UUID, until: datetime | None = None) -> list[str]:
        def hit(a: Attempt) -> bool:
            return a.learner_id == learner_id and (until is None or a.created_at <= until)

        hashes = sorted({a.audio_sha256 for a, _ in self.items if hit(a) and a.audio_sha256})
        self.items = [(replace(a, audio_sha256=None) if hit(a) else a, f) for a, f in self.items]
        return hashes

    async def audio_in_use(self, sha256: str) -> bool:
        return any(a.audio_sha256 == sha256 for a, _ in self.items)

    async def activity(self, learner_id: UUID) -> Mapping[date, int]:
        days: dict[date, int] = {}
        for a, _ in self.items:
            if a.learner_id == learner_id:
                day = a.created_at.date()
                days[day] = days.get(day, 0) + 1
        return days

    async def outcomes(self, learner_id: UUID) -> "list[review.Outcome]":
        """История исходов (ADR-0062): по порядку попыток, местный день — UTC+3, как без
        настроек в БД; засчитано — по вердикту (``is_mastered_verdict``: «ещё раз» не засчитано,
        ADR-0088 п. 7)."""
        from muallim.domain import review  # noqa: PLC0415

        own = sorted(
            (a for a, _ in self.items if a.learner_id == learner_id), key=lambda a: a.created_at
        )
        return [
            review.Outcome(
                a.item_id,
                local_date(a.created_at, DEFAULT_UTC_OFFSET_MIN),
                is_mastered_verdict(a.verdict),
            )
            for a in own
        ]

    async def recent_errors(self, learner_id: UUID, attempts: int) -> list[PronunciationError]:
        """Ошибки последних ``attempts`` попыток ученика (для «букв, где чаще ошибается»)."""
        own = [a for a, _ in self.items if a.learner_id == learner_id]
        own.sort(key=lambda a: a.created_at)
        recent = own[-attempts:] if attempts > 0 else []
        return [e for a in recent for e in a.assessment.errors]


@dataclass
class InMemoryAudio:
    files: dict[str, bytes] = field(default_factory=dict)
    journal: list[str] = field(default_factory=list)  # общий с SpyUoW: порядок commit/удаления

    parts: dict[str, str] = field(default_factory=dict)  # sha → "train" / "test" (TD-FN-174)

    async def save(self, audio: bytes, part: Any = None) -> str:
        import hashlib  # noqa: PLC0415

        sha = hashlib.sha256(audio).hexdigest()
        self.files[sha] = audio
        self.parts[sha] = getattr(part, "value", "train")
        return sha

    async def delete(self, sha256: str) -> None:
        self.journal.append(f"delete:{sha256}")
        self.files.pop(sha256, None)

    async def read(self, sha256: str) -> bytes | None:
        return self.files.get(sha256)


@dataclass
class ScriptedRecognizer:
    """Возвращает заранее заданное «услышанное»; эталон — текст карточки."""

    heard: str | None = None
    fail: bool = False
    fail_stage: str = "model"

    async def recognize(self, audio: bytes, text: str) -> Recognition:
        if self.fail:
            raise RecognitionError("битая запись", stage=self.fail_stage)
        heard = text if self.heard is None else self.heard
        return Recognition(
            heard=heard,
            references=(("wasl", text + "\u064e"), ("waqf", text)),
            model_version="scripted",
            audio_duration_ms=1500,
            raw={"phonemes": heard},
        )


UNHEARD = -1000.0  # балл варианта, которого нет в таблице ScriptedCardListener


def _maroof_cards() -> dict[str, tuple[str, str]]:
    """Текст карточки → (wasl, waqf) в записи фонетизатора бота: фикстура уроков 1–41
    (`tests/fixtures/maroof_cards.json`), фонетизатора в тестах нет."""
    import json  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    path = Path(__file__).resolve().parent / "fixtures" / "maroof_cards.json"
    cards = json.loads(path.read_text(encoding="utf-8"))
    return {c["text"]: (c["wasl"], c["waqf"]) for c in cards}


@dataclass
class ScriptedCardListener:
    """Слушатель «вариантов карточки» без модели (FR-70, ADR-0088 п. 1).

    Эталоны wasl/waqf — как у фонетизатора бота (фикстура; ``references`` — свои, для карточек
    вне фикстуры); балл варианта — по его звукам MostafaMaroof (``to_maroof``), как у настоящей
    модели: таблица ``scores`` задаётся записями бота, варианты с теми же звуками получают тот же
    балл, остальные — ``unheard`` (``-math.inf`` — как у настоящей CTC, когда вариант невозможен).
    ``long_is_short`` — как ``ctc.prepare``: долгая гласная (aa ii uu) для модели — короткая.
    """

    scores: Mapping[str, float] = field(default_factory=dict)
    raw: str = "b u"
    fail: bool = False
    fail_stage: str = "model"
    unheard: float = UNHEARD
    references: tuple[tuple[str, str], ...] | None = None
    calls: list[tuple[str, bool]] = field(default_factory=list)  # (текст, long_is_short)
    single_calls: int = 0  # сколько раз звали поштучный score
    many_calls: list[int] = field(default_factory=list)  # score_many: сколько вариантов за вызов

    async def listen(self, audio: bytes, text: str, *, long_is_short: bool) -> "Listening":
        from muallim.application.ports.recognition import Listening  # noqa: PLC0415
        from muallim.infrastructure.asr.maroof_script import to_maroof  # noqa: PLC0415

        self.calls.append((text, long_is_short))
        if self.fail:
            raise RecognitionError("битая запись", stage=self.fail_stage)
        references: tuple[tuple[str, str], ...]
        if self.references is None:
            wasl, waqf = _maroof_cards()[text]
            references = (("wasl", wasl), ("waqf", waqf))
        else:
            references = self.references

        def sounds(variant: str) -> tuple[str, ...]:
            out = to_maroof(variant)
            if long_is_short:  # aa → a, ii → i, uu → u
                out = tuple(s[0] if s in ("aa", "ii", "uu") else s for s in out)
            return out

        by_sounds = {sounds(k): v for k, v in self.scores.items()}

        def score(variant: str) -> float:
            self.single_calls += 1
            return by_sounds.get(sounds(variant), self.unheard)

        def score_many(variants: Sequence[str]) -> list[float]:
            self.many_calls.append(len(variants))
            return [by_sounds.get(sounds(v), self.unheard) for v in variants]

        # score_many — поле порта из блокера ревью (батч-CTC); пока его нет у Listening —
        # не передаём, чтобы прежние тесты сценария работали
        extra: dict[str, Any] = (
            {"score_many": score_many}
            if "score_many" in {f.name for f in fields(Listening)}
            else {}
        )
        return Listening(
            references=references,
            model_version="scripted-maroof",
            audio_duration_ms=1200,
            raw=self.raw,
            score=score,
            sounds=sounds,
            **extra,
        )


@dataclass
class InMemorySuraReadings:
    """Чтения сур целиком и наизусть (FR-60)."""

    items: list[SuraReading] = field(default_factory=list)

    async def add(self, reading: SuraReading) -> None:
        self.items.append(reading)

    async def count(self, learner_id: UUID, sura: int, mode: SuraMode) -> int:
        return sum(
            r.learner_id == learner_id and r.sura == sura and r.mode is mode for r in self.items
        )

    async def last_read(self, learner_id: UUID, sura: int) -> datetime | None:
        times = [r.created_at for r in self.items if r.learner_id == learner_id and r.sura == sura]
        return max(times, default=None)

    async def memorized(self, learner_id: UUID) -> frozenset[int]:
        return frozenset(
            r.sura
            for r in self.items
            if r.learner_id == learner_id and r.mode is SuraMode.MEMORY and r.passed
        )

    async def credited(self, learner_id: UUID) -> frozenset[str]:
        return frozenset(i for r in self.items if r.learner_id == learner_id for i in r.credited)

    async def audio_hashes(self, learner_id: UUID) -> list[str]:
        return [r.audio_sha256 for r in self.items if r.learner_id == learner_id and r.audio_sha256]


@dataclass
class ScriptedSuraRecognizer:
    """Читает суру по сценарию: слова эталона — слова текста; ``skip_ayah`` — пропустить аят."""

    skip_ayah: int | None = None
    fail: bool = False
    calls: list[tuple[tuple[str, int, str], ...]] = field(default_factory=list)
    preambles: list[str] = field(default_factory=list)

    async def recognize_sura(
        self,
        audio: bytes,
        ayahs: Sequence[tuple[str, int, str]],
        opening: str = "",
        preamble: str = "",
    ) -> SuraRecognition:
        self.calls.append(tuple(ayahs))
        self.preambles.append(preamble)
        if self.fail:
            raise RecognitionError("битая запись")
        refs = tuple(AyahReference(i, n, tuple(text.split(" "))) for i, n, text in ayahs)
        heard = "".join(r.text for r in refs if r.number != self.skip_ayah)
        half = len(heard) // 2
        return SuraRecognition(
            heard=heard,
            ayahs=refs,
            opening=tuple(opening.split(" ")) if opening else (),
            preamble=tuple(preamble.split(" ")) if preamble else (),
            pauses=(),
            chunks=((0, 6000, 0, half), (6000, 12000, half, len(heard))),
            model_version="scripted",
            audio_duration_ms=12000,
        )


SURA_SCORE_RIGHT = -1.0  # балл верного чтения аята у ScriptedSuraListener
# Балл всех остальных вариантов аята по исходу, который должен выйти у `decide` с CardPolicy():
# верное −1 против −20 — «засчитано»; против 0 — маржа ≈ −0,3: «ещё раз»; против 10 — маржа
# ≈ −10 (ниже other_error): «ошибка»
_SURA_RIVAL = {"passed": -20.0, "again": 0.0, "error": 10.0}


@dataclass
class ScriptedSuraListener:
    """Сура на «вариантах карточки» без модели (FR-70 ч. 7, FR-57; ADR-0088 «Суры»).

    Исход каждого аята задаётся сценарием: ``first`` — номер аята → ``passed`` | ``again`` |
    ``error`` | ``unheard`` (тишина: все варианты −inf) | ``broken`` (баллы бросают KeyError) |
    ``skipped`` / ``not_reached`` (аят
    пропущен или не дочитан — отрезка нет; что именно, сценарий решает по соседям).
    Нет в таблице — ``passed``. Верные чтения аята — его текст из программы (слитно и с
    остановкой одинаково); баллы подобраны так, чтобы `decide` дал нужный исход.
    ``second`` — исход второго прохода (аят, вырезанный и услышанный отдельно); нет — как
    ``first``. ``reheard`` — какие аяты слушали вторым проходом (порядок вызовов).
    """

    first: Mapping[int, str] = field(default_factory=dict)
    second: Mapping[int, str] = field(default_factory=dict)
    prefix: tuple[str, ...] = ()  # что прозвучало перед сурой: "preamble", "opening"
    fail: bool = False
    fail_stage: str = "model"
    error: Exception | None = None  # необработанный сбой адаптера (не RecognitionError)
    calls: list[dict[str, Any]] = field(default_factory=list)
    reheard: list[int] = field(default_factory=list)

    @staticmethod
    def _listening(text: str, how: str) -> "Listening":
        import math  # noqa: PLC0415

        from muallim.application.ports.recognition import Listening  # noqa: PLC0415

        if how == "broken":  # звука нет в словаре модели — сбой на подсчёте баллов

            def score(variant: str) -> float:
                raise KeyError("sh")

        else:
            rival = -math.inf if how == "unheard" else _SURA_RIVAL[how]
            right = -math.inf if how == "unheard" else SURA_SCORE_RIGHT

            def score(variant: str) -> float:
                return right if variant == text else rival

        def score_many(variants: Sequence[str]) -> list[float]:
            return [score(v) for v in variants]

        return Listening(
            references=(("wasl", text), ("waqf", text)),
            model_version="scripted-maroof-sura",
            audio_duration_ms=3000,
            raw="second",
            score=score,
            sounds=tuple,
            score_many=score_many,
        )

    async def listen_sura(
        self,
        audio: bytes,
        ayahs: Sequence[tuple[str, int, str]],
        opening: str,
        preamble: str,
        *,
        long_is_short: bool,
    ) -> Any:
        from muallim.application.ports.recognition import (  # noqa: PLC0415
            AyahListening,
            SuraListening,
        )

        self.calls.append(
            {
                "ayahs": tuple(ayahs),
                "opening": opening,
                "preamble": preamble,
                "long_is_short": long_is_short,
            }
        )
        if self.fail:
            raise RecognitionError("битая запись", stage=self.fail_stage)
        if self.error is not None:
            raise self.error
        out = []
        for k, (item_id, number, text) in enumerate(ayahs):
            how = self.first.get(number, "passed")
            reached = how not in ("not_reached", "skipped")
            first = self._listening(text, how if reached else "unheard")

            async def rehear(number: int = number, text: str = text, how: str = how) -> Any:
                self.reheard.append(number)
                return self._listening(text, self.second.get(number, how))

            out.append(
                AyahListening(
                    item_id=item_id,
                    number=number,
                    references=first.references,
                    raw=f"ayah {number}",
                    score=first.score,
                    sounds=first.sounds,
                    score_many=first.score_many,
                    span_ms=(k * 3000, (k + 1) * 3000) if reached else None,
                    rehear=rehear if reached else None,
                )
            )
        return SuraListening(
            ayahs=tuple(out),
            prefix=self.prefix,
            raw="whole sura",
            model_version="scripted-maroof-sura",
            audio_duration_ms=3000 * len(ayahs),
        )


@dataclass
class ListErasureLog:
    """Журнал удалений в памяти; пишет в общий журнал «erase:<действие>» — проверяем порядок."""

    entries: list[tuple[ErasureAction, UUID]] = field(default_factory=list)
    journal: list[str] = field(default_factory=list)

    async def record(self, action: ErasureAction, learner_id: UUID) -> None:
        self.entries.append((action, learner_id))
        self.journal.append(f"erase:{action}")


@dataclass
class SpyUoW:
    commits: int = 0
    journal: list[str] = field(default_factory=list)

    async def commit(self) -> None:
        self.commits += 1
        self.journal.append("commit")

    async def rollback(self) -> None:
        pass


@dataclass
class ListEventLog:
    events: list[tuple[str, UUID | None, dict[str, str | int | None]]] = field(default_factory=list)

    async def record(
        self, event: str, learner_id: UUID | None, payload: dict[str, str | int | None]
    ) -> None:
        self.events.append((event, learner_id, payload))


@dataclass
class InMemoryReferenceAudio:
    files: dict[str, bytes] = field(default_factory=dict)

    def has(self, item_id: str) -> bool:
        return item_id in self.files

    async def get(self, item_id: str) -> bytes | None:
        return self.files.get(item_id)

    async def save(self, item_id: str, audio: bytes) -> None:
        self.files[item_id] = audio


@dataclass
class InMemoryVideos:
    """Ролики «🎬 Как произносить» (ADR-0074): текст карточки → ключ, буква → ключ тройки.

    Ролик — 1280×720, 4,5 с; байты — ``b"mp4:" + ключ``.
    """

    texts: dict[str, str] = field(default_factory=dict)
    letters: dict[str, str] = field(default_factory=dict)

    def for_text(self, text: str) -> str | None:
        return self.texts.get(text)

    def for_letter(self, letter: str) -> str | None:
        return self.letters.get(letter)

    async def get(self, key: str) -> "Video | None":
        from muallim.application.ports.storage import Video  # noqa: PLC0415 — нет до FR-56

        if key not in {*self.texts.values(), *self.letters.values()}:
            return None
        return Video(key=key, data=b"mp4:" + key.encode(), seconds=4.5, width=1280, height=720)


@dataclass
class ScriptedReadingGuide:
    """«Как читается» без фонетизатора: фонемы = текст карточки без пробелов; None — не умеет."""

    fail: bool = False

    def phonemes(self, text: str) -> str | None:
        return None if self.fail else text.replace(" ", "")


@dataclass
class InMemoryAnnotators:
    """Разметчики по приглашению: digest → (код, срок, использован ли); привязки Telegram ID."""

    invites: dict[str, tuple[str, datetime, bool]] = field(default_factory=dict)
    bound: dict[int, str] = field(default_factory=dict)
    revoked: set[str] = field(default_factory=set)
    failures: dict[UUID, list[datetime]] = field(default_factory=dict)
    used_codes: set[str] = field(default_factory=set)  # коды из меток Excel и приглашений

    async def bound_code(self, telegram_user_id: int) -> str | None:
        return self.bound.get(telegram_user_id)

    async def is_revoked(self, code: str) -> bool:
        return code in self.revoked

    async def redeem(self, digest: str, telegram_user_id: int, now: datetime) -> str | None:
        found = self.invites.get(digest)
        if found is None or found[2] or found[1] <= now:
            return None
        code, expires, _ = found
        self.invites[digest] = (code, expires, True)
        self.bound[telegram_user_id] = code
        self.revoked.discard(code)
        return code

    async def failed_redeems(self, learner_id: UUID, since: datetime) -> int:
        return sum(1 for at in self.failures.get(learner_id, []) if at >= since)

    async def add_failed_redeem(self, learner_id: UUID, at: datetime) -> None:
        self.failures.setdefault(learner_id, []).append(at)

    async def register(self, telegram_user_id: int, reserved: frozenset[str], now: datetime) -> str:
        if (code := self.bound.get(telegram_user_id)) is not None:
            return code
        taken = reserved | self.used_codes | self.revoked | set(self.bound.values())
        code = next_annotator_code(frozenset(taken))
        self.bound[telegram_user_id] = code
        return code


@dataclass
class InMemoryAnnotationTasks:
    """Очередь разметки: задачи по порядку; метки копятся списком. Клетки меток (FR-62) — по
    попытке, список на каждую метку по порядку: новая метка не стирает клетки прежней."""

    tasks: list[AnnotationTask] = field(default_factory=list)
    labels: list[Label] = field(default_factory=list)
    marks: dict[UUID, list[list["CellMark"]]] = field(default_factory=dict)

    def _open(self, annotator: str) -> list[AnnotationTask]:
        done = {label.attempt_id for label in self.labels if label.annotator == annotator}
        return [t for t in self.tasks if t.attempt_id not in done]

    async def next_for(self, annotator: str, exclude: frozenset[UUID]) -> AnnotationTask | None:
        return next((t for t in self._open(annotator) if t.attempt_id not in exclude), None)

    async def get(self, attempt_id: UUID) -> AnnotationTask | None:
        return next((t for t in self.tasks if t.attempt_id == attempt_id), None)

    async def remaining(self, annotator: str) -> int:
        return len(self._open(annotator))

    async def add(self, label: Label, marks: Sequence["CellMark"] = ()) -> None:
        self.labels.append(label)
        self.marks.setdefault(label.attempt_id, []).append(list(marks))


@dataclass
class InMemoryQuizAnswers:
    """Ответы «🧠 Закрепления» (ADR-0066): строка пишется при показе, ответ — в неё же."""

    rows: dict[UUID, "QuizAnswer"] = field(default_factory=dict)

    async def add(self, row: "QuizAnswer") -> bool:
        """Как UNIQUE (learner_id, round_no, position): место занято — не вставляет."""
        place = (row.learner_id, row.round_no, row.position)
        if any((r.learner_id, r.round_no, r.position) == place for r in self.rows.values()):
            return False
        self.rows[row.id] = row
        return True

    async def get(self, answer_id: UUID) -> "QuizAnswer | None":
        return self.rows.get(answer_id)

    async def record(
        self,
        answer_id: UUID,
        *,
        picked: int | None,
        correct: bool | None,
        answered_at: datetime,
        attempt_id: UUID | None = None,
    ) -> bool:
        """``correct`` = None — вопрос пропущен («Не могу сейчас говорить/слушать»)."""
        row = self.rows.get(answer_id)
        if row is None or row.answered_at is not None:
            return False
        self.rows[answer_id] = replace(
            row, picked=picked, correct=correct, answered_at=answered_at, attempt_id=attempt_id
        )
        return True

    async def history(self, learner_id: UUID) -> "list[QuizAnswer]":
        mine = [r for r in self.rows.values() if r.learner_id == learner_id]
        return sorted(mine, key=lambda r: (r.round_no, r.position))

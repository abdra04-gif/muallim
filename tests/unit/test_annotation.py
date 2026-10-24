"""Разметка в Telegram (FR-17): правила меток, доступ разметчика, приглашения, очередь.

Сценарии — на тестовых портах (tests/fakes.py), без Telegram и БД.
"""

from datetime import timedelta
from uuid import UUID

import pytest

from muallim.application.use_cases.annotation import (
    AnnotatorAccess,
    JoinAnnotation,
    NextAnnotation,
    NotAnnotator,
    RedeemInvite,
    RedeemResult,
    SubmitAnnotation,
)
from muallim.domain.annotation import (
    INVITE_TTL,
    MAX_INVITE_FAILURES,
    AnnotationSource,
    AnnotationStatus,
    AnnotationTask,
    LabelError,
    check_label,
    check_phonemes,
    check_self_correction,
    clean_phonemes,
    invite_digest,
    looks_like_invite,
    next_annotator_code,
    valid_annotator_code,
)
from muallim.domain.learner import Learner
from tests.fakes import (
    FixedClock,
    InMemoryAnnotationTasks,
    InMemoryAnnotators,
    InMemoryAudio,
    ListEventLog,
    SpyUoW,
)

ANNOTATOR_TG, STRANGER_TG = 900, 901


# ---------- правила (домен) ----------
def test_clean_phonemes_drops_spaces_and_invisible_marks() -> None:
    assert clean_phonemes(" \u200fسَ بَ\u200e ") == "سَبَ"


@pytest.mark.parametrize(
    ("text", "hint"),
    [
        ("", "пустое"),
        ("أَ", "хамза пишется одним знаком «ء»"),
        ("بّ", "удвоение"),
        ("sa", "не фонема"),
    ],
)
def test_check_phonemes_explains_what_is_wrong(text: str, hint: str) -> None:
    with pytest.raises(LabelError, match=hint):
        check_phonemes(text)


def test_check_phonemes_accepts_phonetic_alphabet() -> None:
    check_phonemes("صَبَرَ")


def test_agree_must_keep_bot_phonemes_and_fix_must_change_them() -> None:
    check_label(AnnotationStatus.AGREE, "سَ", bot_heard="سَ")
    check_label(AnnotationStatus.FIX, "صَ", bot_heard="سَ")
    with pytest.raises(LabelError, match="agree"):
        check_label(AnnotationStatus.AGREE, "صَ", bot_heard="سَ")
    with pytest.raises(LabelError, match="ничего не исправлено"):
        check_label(AnnotationStatus.FIX, "سَ", bot_heard="سَ")


@pytest.mark.parametrize(
    ("code", "ok"), [("A1", True), ("t-2_b", True), ("", False), ("А1", False)]
)
def test_annotator_code_is_latin(code: str, ok: bool) -> None:  # «А» — кириллица
    assert valid_annotator_code(code) is ok


def test_invite_digest_ignores_case_dashes_and_spaces() -> None:
    assert invite_digest(" kq7m-29fx ") == invite_digest("KQ7M29FX")
    assert invite_digest("KQ7M29FX") != "KQ7M29FX"  # в БД — отпечаток, не сам код
    assert len(invite_digest("KQ7M29FX")) == 64


@pytest.mark.parametrize(
    ("text", "ok"),
    [
        ("KQ7M-29FX-HT3P", True),
        (" kq7m 29fx ht3p ", True),
        ("привет", False),
        ("A2", False),
        ("KQ7M-29FX-HT3", False),
        ("KQ7M-29FX-HT3O", False),
    ],  # O — нет в алфавите приглашений
)
def test_only_invite_shaped_text_after_annotate_is_an_invite(text: str, ok: bool) -> None:
    assert looks_like_invite(text) is ok


# ---------- сценарии ----------
def _learner(tg: int) -> Learner:
    return Learner(UUID(int=tg), tg, f"L-{tg}", "ru", FixedClock().now())


def _task(n: int, heard: str = "سَ", sha: str | None = None) -> AnnotationTask:
    return AnnotationTask(
        attempt_id=UUID(int=n), item_id="L005-03", item_text="صَ", page=15, line=3,
        bot_passed=False, bot_errors=(("ص", "س"),), reference_phonemes="صَ", bot_heard=heard,
        learner_says=None, audio_sha256=sha or f"{n:064x}",
    )  # fmt: skip


class World:
    """Разметчик A1 задан в настройках; очередь из двух записей с файлами."""

    def __init__(self) -> None:
        self.clock = FixedClock()
        self.directory = InMemoryAnnotators()
        self.tasks = InMemoryAnnotationTasks([_task(1), _task(2)])
        self.audio = InMemoryAudio({t.audio_sha256: b"ogg" + bytes([i]) for i, t in
                                    enumerate(self.tasks.tasks)})  # fmt: skip
        self.events, self.uow = ListEventLog(), SpyUoW()
        self.access = AnnotatorAccess(self.directory, {ANNOTATOR_TG: "A1"})

    def next(self) -> NextAnnotation:
        return NextAnnotation(self.access, self.tasks, self.audio, self.events, self.uow)

    def submit(self) -> SubmitAnnotation:
        return SubmitAnnotation(self.access, self.tasks, self.uow, self.events, self.clock)

    def redeem(self) -> RedeemInvite:
        return RedeemInvite(self.directory, self.uow, self.events, self.clock)

    def join(self) -> JoinAnnotation:
        return JoinAnnotation(self.access, self.directory, self.uow, self.events, self.clock)


async def test_access_from_settings_list_and_from_invite() -> None:
    w = World()
    assert await w.access.code_for(ANNOTATOR_TG) == "A1"
    assert await w.access.code_for(STRANGER_TG) is None
    w.directory.bound[STRANGER_TG] = "A2"
    assert await w.access.code_for(STRANGER_TG) == "A2"


async def test_revoked_code_closes_access_even_from_settings() -> None:
    w = World()
    w.directory.revoked.add("A1")
    assert await w.access.code_for(ANNOTATOR_TG) is None


async def test_invite_grants_access_once_and_expires() -> None:
    w = World()
    expires = w.clock.current + INVITE_TTL
    w.directory.invites[invite_digest("KQ7M29FX")] = ("A2", expires, False)
    learner = _learner(STRANGER_TG)

    assert await w.redeem().execute(learner, "kq7m-29fx") == (RedeemResult.GRANTED, "A2")
    assert await w.access.code_for(STRANGER_TG) == "A2"
    other = _learner(902)  # тот же код второй раз не сработает
    assert await w.redeem().execute(other, "KQ7M29FX") == (RedeemResult.INVALID, None)
    assert ("annotator_invite_redeemed", learner.id, {"annotator": "A2"}) in w.events.events

    w.directory.invites[invite_digest("OLD1OLD1")] = ("A3", w.clock.current, False)
    w.clock.current += timedelta(seconds=5)
    assert await w.redeem().execute(other, "OLD1OLD1") == (RedeemResult.INVALID, None)


async def test_guessing_invites_is_locked_after_several_failures() -> None:
    w = World()
    w.directory.invites[invite_digest("GOODCODE")] = ("A2", w.clock.current + INVITE_TTL, False)
    learner = _learner(STRANGER_TG)
    for _ in range(MAX_INVITE_FAILURES):
        assert (await w.redeem().execute(learner, "WRONG"))[0] is RedeemResult.INVALID
    # даже верный код не принимается, пока не пройдёт час
    assert await w.redeem().execute(learner, "GOODCODE") == (RedeemResult.LOCKED, None)
    assert await w.access.code_for(STRANGER_TG) is None


async def test_stranger_gets_no_task_and_cannot_label() -> None:
    w = World()
    with pytest.raises(NotAnnotator):
        await w.next().execute(_learner(STRANGER_TG))
    with pytest.raises(NotAnnotator):
        await w.submit().execute(_learner(STRANGER_TG), UUID(int=1), AnnotationStatus.AGREE)
    assert w.tasks.labels == []


async def test_next_task_comes_with_recording_and_count_left() -> None:
    w = World()
    shown = await w.next().execute(_learner(ANNOTATOR_TG))
    assert shown is not None
    assert shown.task.attempt_id == UUID(int=1) and shown.audio == b"ogg\x00"
    assert shown.annotator == "A1" and shown.remaining == 2
    # пропущенную запись в этот раз не показываем снова
    skipped = await w.next().execute(_learner(ANNOTATOR_TG), exclude=frozenset({UUID(int=1)}))
    assert skipped is not None and skipped.task.attempt_id == UUID(int=2)


async def test_task_without_recording_file_is_skipped() -> None:
    w = World()
    del w.audio.files[w.tasks.tasks[0].audio_sha256]
    shown = await w.next().execute(_learner(ANNOTATOR_TG))
    assert shown is not None and shown.task.attempt_id == UUID(int=2)


async def test_queue_is_empty_when_everything_is_labelled() -> None:
    w = World()
    for n in (1, 2):
        await w.submit().execute(_learner(ANNOTATOR_TG), UUID(int=n), AnnotationStatus.AGREE)
    assert await w.next().execute(_learner(ANNOTATOR_TG)) is None


async def test_agree_saves_bot_phonemes_with_source_and_time() -> None:
    w = World()
    saved = await w.submit().execute(
        _learner(ANNOTATOR_TG), UUID(int=1), AnnotationStatus.AGREE, seconds_spent=7
    )
    assert saved
    (label,) = w.tasks.labels
    assert (label.annotator, label.status, label.actual) == ("A1", AnnotationStatus.AGREE, "سَ")
    assert label.source is AnnotationSource.TELEGRAM and label.seconds_spent == 7
    assert w.uow.commits == 1
    assert w.events.events[-1][0] == "annotation_submitted"


async def test_fix_is_checked_like_the_excel_package() -> None:
    w = World()
    submit, me = w.submit(), _learner(ANNOTATOR_TG)
    with pytest.raises(LabelError, match="хамза"):
        await submit.execute(me, UUID(int=1), AnnotationStatus.FIX, actual="أَ")
    with pytest.raises(LabelError, match="ничего не исправлено"):
        await submit.execute(me, UUID(int=1), AnnotationStatus.FIX, actual="سَ")
    assert w.tasks.labels == []
    assert await submit.execute(me, UUID(int=1), AnnotationStatus.FIX, actual=" صَ\u200f")
    assert w.tasks.labels[-1].actual == "صَ"


async def test_unusable_audio_has_no_phonemes() -> None:
    w = World()
    await w.submit().execute(_learner(ANNOTATOR_TG), UUID(int=1), AnnotationStatus.AUDIO_UNUSABLE)
    assert w.tasks.labels[-1].actual is None


async def test_label_for_deleted_attempt_is_not_saved() -> None:
    w = World()
    gone = await w.submit().execute(_learner(ANNOTATOR_TG), UUID(int=99), AnnotationStatus.AGREE)
    assert gone is False and w.tasks.labels == []


# ---------- открытый вход по /annotate (решение автора 2026-10-24) ----------
@pytest.mark.parametrize(
    ("taken", "expected"),
    [
        (set(), "A1"),
        ({"A1", "A2"}, "A3"),
        ({"A1", "A7", "t-2_b"}, "A8"),  # номер — после наибольшего, дыры не занимаются
        ({"a5", "A01"}, "A1"),  # чужие написания не считаются: только «A» и число без нулей
    ],
)
def test_next_annotator_code_never_reuses_a_code(taken: set[str], expected: str) -> None:
    assert next_annotator_code(frozenset(taken)) == expected
    assert valid_annotator_code(expected)


async def test_anyone_who_writes_annotate_joins_with_new_code() -> None:
    w = World()  # A1 уже есть в настройках — новичок получает A2
    newcomer = _learner(STRANGER_TG)
    assert await w.join().execute(newcomer) == ("A2", True)
    assert await w.access.code_for(STRANGER_TG) == "A2"
    assert ("annotator_joined", newcomer.id, {"annotator": "A2"}) in w.events.events
    assert w.uow.commits == 1
    shown = await w.next().execute(newcomer)  # и сразу может размечать
    assert shown is not None and shown.annotator == "A2"


async def test_joining_again_keeps_the_same_code() -> None:
    w = World()
    newcomer = _learner(STRANGER_TG)
    await w.join().execute(newcomer)
    assert await w.join().execute(newcomer) == ("A2", False)
    assert await w.join().execute(_learner(ANNOTATOR_TG)) == ("A1", False)  # из настроек
    assert [e for e in w.events.events if e[0] == "annotator_joined"] == [
        ("annotator_joined", newcomer.id, {"annotator": "A2"})
    ]


async def test_revoked_annotator_cannot_join_again() -> None:
    """Открытый вход не обходит отзыв: annotator-revoke по-прежнему закрывает доступ."""
    w = World()
    w.directory.bound[STRANGER_TG] = "A2"
    w.directory.revoked.add("A2")
    w.directory.revoked.add("A1")
    assert await w.join().execute(_learner(STRANGER_TG)) is None
    assert await w.join().execute(_learner(ANNOTATOR_TG)) is None
    assert await w.access.code_for(STRANGER_TG) is None
    assert not any(e[0] == "annotator_joined" for e in w.events.events)


async def test_new_codes_skip_codes_used_anywhere() -> None:
    """Код из Excel-разметки или приглашения новичку не достаётся: метки людей не смешаются."""
    w = World()
    w.directory.used_codes.update({"A2", "A5"})
    assert await w.join().execute(_learner(STRANGER_TG)) == ("A6", True)


async def test_labelled_record_can_be_shown_again_to_redo_the_answer() -> None:
    w = World()
    me = _learner(ANNOTATOR_TG)
    await w.submit().execute(me, UUID(int=1), AnnotationStatus.AGREE)
    again = await w.next().again(me, UUID(int=1))
    assert again is not None
    assert again.task.attempt_id == UUID(int=1) and again.audio == b"ogg\x00"
    # новая метка — рядом со старой; в данных берётся последняя метка разметчика
    await w.submit().execute(me, UUID(int=1), AnnotationStatus.FIX, actual="صَ")
    assert [lb.status for lb in w.tasks.labels] == [AnnotationStatus.AGREE, AnnotationStatus.FIX]
    assert await w.next().again(me, UUID(int=99)) is None  # запись удалена
    with pytest.raises(NotAnnotator):
        await w.next().again(_learner(STRANGER_TG), UUID(int=1))


# ---------- самоисправление: отдельная категория (решение автора 2026-10-18, SRC-068) ----------
def test_self_correction_only_where_reading_can_be_judged() -> None:
    """«Сам исправился» — про чтение; у плохой записи и чужого текста чтения не слышно."""
    for status in (AnnotationStatus.AGREE, AnnotationStatus.FIX):
        check_self_correction(status, self_corrected=True)
    for status in AnnotationStatus:
        check_self_correction(status, self_corrected=False)
    for status in (AnnotationStatus.AUDIO_UNUSABLE, AnnotationStatus.OFF_TASK):
        with pytest.raises(LabelError, match="сам исправился"):
            check_self_correction(status, self_corrected=True)


async def test_self_correction_is_saved_beside_agree_and_fix() -> None:
    """Отдельно от «бот прав / бот ошибся»: ответ модели оценивается как обычно."""
    w = World()
    submit, me = w.submit(), _learner(ANNOTATOR_TG)
    await submit.execute(me, UUID(int=1), AnnotationStatus.AGREE, self_corrected=True)
    await submit.execute(me, UUID(int=2), AnnotationStatus.FIX, actual="صَ", self_corrected=True)
    assert [(lb.status, lb.self_corrected) for lb in w.tasks.labels] == [
        (AnnotationStatus.AGREE, True), (AnnotationStatus.FIX, True),
    ]  # fmt: skip
    with pytest.raises(LabelError):
        await submit.execute(me, UUID(int=1), AnnotationStatus.OFF_TASK, self_corrected=True)
    assert len(w.tasks.labels) == 2


async def test_without_mark_reading_is_not_self_corrected() -> None:
    w = World()
    await w.submit().execute(_learner(ANNOTATOR_TG), UUID(int=1), AnnotationStatus.AGREE)
    assert w.tasks.labels[-1].self_corrected is False


# ---------- настройки ----------
def test_annotators_from_settings() -> None:
    from pydantic import SecretStr  # noqa: PLC0415

    from muallim.bootstrap.config import Settings  # noqa: PLC0415

    settings = Settings(bot_token=SecretStr("0:t"), annotator_ids=" A1:900, A2 : 901 ,")
    assert settings.annotators == {900: "A1", 901: "A2"}
    assert Settings(bot_token=SecretStr("0:t"), _env_file=None).annotators == {}  # не из .env
    for bad in ("A1", "A1:x", "А1:900", "A1:900,A2:900"):  # без ID, не число, кириллица, дубль
        with pytest.raises(ValueError, match="ANNOTATOR_IDS"):
            _ = Settings(bot_token=SecretStr("0:t"), annotator_ids=bad).annotators

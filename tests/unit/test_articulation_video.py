"""FR-56 (ADR-0074): ролик «🎬 Как произносить» — сценарии и экраны, без Telegram и файлов.

Решения автора 2026-10-25: где для текста карточки есть ролик — только ролик (кнопки 🔊 нет,
вместо неё «🎬 Как произносить»; после попытки — тоже ролик); где ролика нет — как было (FR-20).
Разбор ошибки (FR-54): ошибка в одном слоге — ролик этого (нужного) слога, нет такого ролика или
группа в нескольких слогах — тройка буквы; хамза (أ, إ) — тройка أ; у буквы без роликов кнопки
нет. Ролик после попытки и ролик разбора совпали — одна кнопка (из разбора). Шпаргалка (FR-52):
у буквы с тройкой — только 🎬, без 🔊.

Ролик отдаёт ``GetArticulationVideo`` без записи в журнал; просмотр пишет ``RecordVideoPlayed``
— только после того, как ролик ушёл в Telegram (сбой отправки — события нет).

Ролики — ``InMemoryVideos`` (ключи выдуманы, тексты — из curriculum/course.ru.yaml); оценка —
готовая ``assess``; картинки не рисуются.
"""

from typing import Any
from uuid import UUID

import pytest
from aiogram.types import InlineKeyboardMarkup

from muallim.application.breakdown import build_breakdown
from muallim.application.feedback import FeedbackRenderer
from muallim.application.use_cases.recitation import RecitationResult
from muallim.domain.assessment import assess, unread_from
from muallim.domain.attempt import Attempt
from muallim.domain.curriculum import Curriculum, ItemKind, Lesson, LessonItem, lesson_letter
from muallim.domain.learner import Learner
from muallim.domain.policy import GradingPolicy
from muallim.presentation.telegram import callbacks as cb
from muallim.presentation.telegram import render, screens, texts
from tests.fakes import (
    FixedClock,
    InMemoryLearners,
    InMemoryVideos,
    ListEventLog,
    SequentialIds,
    SpyUoW,
)

RA = "L004-02"  # رَ — слог урока ر, ролик есть
RI = "L004-03"  # رِ
RA_TRIPLE = "L004-05"  # رَ رِ رُ — тройка
RA_LINE = "L004-06"  # رَرْ رِرْ رُرْ أَرْ إِرْ أُرْ — у строки ролика нет
ZAY_LINE = "L005-06"  # أَزْ إِزْ أُزْ زَرْ زِرْ زُرْ
MA = "L006-02"  # مَ — у م роликов нет
MIM, AFTER_LETTERS = "L006", "L031"
MIM_LINE = "L006-06"  # أَمْ إِمْ أُمْ مُرْ مُزْ رُمْ أَمَرَ أُمِرَ أَمْرُ

VIDEO_BUTTON = "🎬 Как произносить"  # подпись утвердил автор 2026-10-25
TRIPLE_LETTERS = ("أ", "ر", "ز")


def _videos() -> InMemoryVideos:
    """Как в curriculum/video/videos.yaml: 9 слогов и 3 тройки (буквы أ ر ز)."""
    syllables = ("أَ", "إِ", "أُ", "رَ", "رِ", "رُ", "زَ", "زِ", "زُ")
    triples = {"أ": "أَ إِ أُ", "ر": "رَ رِ رُ", "ز": "زَ زِ زُ"}
    by_text = {t: f"s{k}" for k, t in enumerate(syllables)}
    by_text |= {t: f"t-{k}" for k, t in enumerate(triples.values())}
    return InMemoryVideos(by_text, {letter: by_text[t] for letter, t in triples.items()})


@pytest.fixture(autouse=True)
def _captions_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(render, "available", lambda: False)


def _buttons(kb: InlineKeyboardMarkup) -> list[tuple[str, str]]:
    return [(b.text, b.callback_data or "") for row in kb.inline_keyboard for b in row]


def _video_datas(kb: InlineKeyboardMarkup) -> list[str]:
    return [d for _, d in _buttons(kb) if d.startswith(cb.Watch.__prefix__ + ":")]


def _watched(kb: InlineKeyboardMarkup) -> list[str]:
    """Ключи роликов, на которые ведут кнопки 🎬 экрана, по порядку."""
    return [cb.Watch.unpack(d).v for d in _video_datas(kb)]


def _listen(kb: InlineKeyboardMarkup) -> list[str]:
    return [d for _, d in _buttons(kb) if d.startswith(cb.Listen.__prefix__ + ":")]


def test_video_button_text_is_the_one_approved_by_author() -> None:
    assert texts.VIDEO_BUTTON == VIDEO_BUTTON


# ---------- сценарии: ролик и запись просмотра ----------
async def _learner() -> Learner:
    from muallim.application.use_cases.learners import EnsureLearner  # noqa: PLC0415

    learner, _ = await EnsureLearner(
        InMemoryLearners(), SpyUoW(), FixedClock(), SequentialIds(), ListEventLog()
    ).execute(42, "ru")
    return learner


async def test_video_is_returned_by_key() -> None:
    from muallim.application.use_cases.video import GetArticulationVideo  # noqa: PLC0415

    videos = _videos()
    key = videos.for_text("رَ")
    assert key is not None
    video = await GetArticulationVideo(videos).execute(key)
    assert video is not None
    assert (video.key, video.width, video.height) == (key, 1280, 720)
    assert video.data and video.seconds > 0


async def test_unknown_video_is_none() -> None:
    from muallim.application.use_cases.video import GetArticulationVideo  # noqa: PLC0415

    assert await GetArticulationVideo(_videos()).execute("нет-такого") is None


async def test_watching_is_logged_with_card_and_source() -> None:
    from muallim.application.use_cases.video import RecordVideoPlayed  # noqa: PLC0415

    learner, events, uow = await _learner(), ListEventLog(), SpyUoW()
    await RecordVideoPlayed(uow, events).execute(learner, "s3", source="card", item_id=RA)
    assert events.events == [
        ("video_played", learner.id, {"video": "s3", "item_id": RA, "from": "card"})
    ]
    assert uow.commits == 1


async def test_watching_from_sheet_is_logged_with_letter() -> None:
    from muallim.application.use_cases.video import RecordVideoPlayed  # noqa: PLC0415

    learner, events = await _learner(), ListEventLog()
    await RecordVideoPlayed(SpyUoW(), events).execute(learner, "t-1", source="sheet", letter="ر")
    assert events.events == [
        ("video_played", learner.id, {"video": "t-1", "letter": "ر", "from": "sheet"})
    ]


@pytest.mark.parametrize("source", ["card", "auto", "after", "breakdown"])
async def test_watching_source_is_written_as_from(source: str) -> None:
    from muallim.application.use_cases.video import RecordVideoPlayed  # noqa: PLC0415

    learner, events = await _learner(), ListEventLog()
    await RecordVideoPlayed(SpyUoW(), events).execute(
        learner, "s7", source=source, item_id="L005-03"
    )
    assert events.events[-1][2]["from"] == source


# ---------- карточка ----------
def _card(c: Curriculum, item_id: str, *, has_audio: bool = True, **kw: Any) -> screens.Screen:
    return screens.card(c, c.item(item_id), has_audio, False, **kw)


@pytest.mark.parametrize("item_id", [RA, RA_TRIPLE, "L003-04", "L005-03"])
def test_card_with_video_has_video_button_instead_of_listen(
    curriculum: Curriculum, item_id: str
) -> None:
    """Звук «как правильно» есть, но у текста карточки есть ролик — только ролик."""
    videos = _videos()
    s = _card(curriculum, item_id, videos=videos)
    assert _listen(s.keyboard) == []
    assert texts.LISTEN_BUTTON not in [t for t, _ in _buttons(s.keyboard)]
    assert _watched(s.keyboard) == [videos.for_text(curriculum.item(item_id).text)]
    video = [t for t, d in _buttons(s.keyboard) if d in _video_datas(s.keyboard)]
    assert video == [texts.VIDEO_BUTTON]


def test_card_with_video_but_without_reference_sound_has_video_button(
    curriculum: Curriculum,
) -> None:
    videos = _videos()
    s = _card(curriculum, RI, has_audio=False, videos=videos)
    assert _watched(s.keyboard) == [videos.for_text("رِ")]
    assert _listen(s.keyboard) == []


@pytest.mark.parametrize("item_id", [MA, RA_LINE, MIM_LINE])
def test_card_without_video_keeps_listen_button(curriculum: Curriculum, item_id: str) -> None:
    """Регрессия FR-20: у текста нет ролика — 🔊 как было, 🎬 нет."""
    s = _card(curriculum, item_id, videos=_videos())
    assert _listen(s.keyboard) == [cb.Listen(item_id=item_id).pack()]
    assert _watched(s.keyboard) == []


def test_card_without_any_reference_or_video_has_neither(curriculum: Curriculum) -> None:
    s = _card(curriculum, MA, has_audio=False, videos=_videos())
    assert _listen(s.keyboard) == [] and _watched(s.keyboard) == []


def test_card_video_callback_carries_card_source(curriculum: Curriculum) -> None:
    """Для журнала (video_played): с карточки — from=card и id карточки."""
    [data] = _video_datas(_card(curriculum, RA, videos=_videos()).keyboard)
    assert len(data.encode()) <= 64
    assert RA in data and "card" in data


# ---------- результат попытки и разбор ошибки (FR-54) ----------
def _result(c: Curriculum, renderer: FeedbackRenderer, item_id: str, heard: str = "") -> Any:
    item = c.item(item_id)
    heard = heard or item.text
    a = assess(item.text, heard)
    unread = unread_from(a.reference, heard)
    attempt = Attempt(
        UUID(int=1), UUID(int=2), item.id, "v", "stub", a, GradingPolicy().verdict(a),
        None, None, 1, FixedClock().now(),
    )  # fmt: skip
    review = build_breakdown(
        a, item.text, c.lexicon, unread=unread, lesson_letter=lesson_letter(c.locate(item_id)[0])
    )
    return RecitationResult(
        item, attempt, renderer.explain(a.errors, a.reference, unread), "", c.next_item(item.id),
        unread_from=unread, breakdown=review,
    )  # fmt: skip


def _shown(c: Curriculum, renderer: FeedbackRenderer, item_id: str, heard: str,
           videos: InMemoryVideos | None = None) -> screens.Screen:  # fmt: skip
    r = _result(c, renderer, item_id, heard)
    assert r.breakdown.groups, "оценка нашла ошибку"
    return screens.result(c, r, True, videos=videos or _videos())


def test_result_with_video_offers_video_instead_of_listen(
    curriculum: Curriculum, renderer: FeedbackRenderer
) -> None:
    """После попытки, где раньше был 🔊 «как правильно», — ролик (ошибок нет)."""
    videos = _videos()
    s = screens.result(curriculum, _result(curriculum, renderer, RA), True, videos=videos)
    assert _listen(s.keyboard) == []
    assert _watched(s.keyboard) == [videos.for_text("رَ")]
    [data] = _video_datas(s.keyboard)
    assert (texts.VIDEO_BUTTON, data) in _buttons(s.keyboard)
    assert "after" in data


def test_result_without_video_keeps_listen(
    curriculum: Curriculum, renderer: FeedbackRenderer
) -> None:
    s = screens.result(curriculum, _result(curriculum, renderer, MA), True, videos=_videos())
    assert _listen(s.keyboard) == [cb.Listen(item_id=MA).pack()]
    assert _watched(s.keyboard) == []


@pytest.mark.parametrize(
    ("item_id", "heard"),
    [
        (RA_LINE, "رَرْ لِرْ رُرْ أَرْ إِرْ أُرْ"),  # ر → ل
        (RA_LINE, "رَرْ رَرْ رُرْ أَرْ إِرْ أُرْ"),  # огласовка
        (RA_LINE, "رَرْ لِرْ لُرْ أَرْ إِرْ أُرْ"),  # одна группа в двух слогах
        (ZAY_LINE, "أَزْ عِزْ أُزْ زَرْ زِرْ زُرْ"),  # хамза
        (MIM_LINE, "أَمْ إِمْ أُمْ مُرْ مُزْ رُمْ أَمَرَ أُمِرَ أَمْلُ"),
    ],
)
def test_breakdown_shows_no_video(
    curriculum: Curriculum, renderer: FeedbackRenderer, item_id: str, heard: str
) -> None:
    """Решение автора 2026-10-25 (уточнение): ролики — только на карточках алфавита;
    в разборе строк и сур кнопок 🎬 нет, чтобы не путать ученика."""
    s = _shown(curriculum, renderer, item_id, heard, _videos())
    assert _watched(s.keyboard) == []


def test_error_on_card_with_video_offers_only_that_card_video(
    curriculum: Curriculum, renderer: FeedbackRenderer
) -> None:
    """Карточка «رِ», прочитано «لِ»: после попытки — ролик самой карточки, без разбора."""
    videos = _videos()
    s = _shown(curriculum, renderer, RI, "لِ", videos)
    assert _watched(s.keyboard) == [videos.for_text("رِ")]
    [data] = _video_datas(s.keyboard)
    assert "after" in data and "breakdown" not in data


def test_error_on_triple_card_offers_only_the_triple(
    curriculum: Curriculum, renderer: FeedbackRenderer
) -> None:
    videos = _videos()
    s = _shown(curriculum, renderer, RA_TRIPLE, "رَ لِ رُ", videos)
    assert _watched(s.keyboard) == [videos.for_text("رَ رِ رُ")]


# ---------- шпаргалка (FR-52) ----------
def _head(lesson: Lesson) -> LessonItem:
    return next(i for i in lesson.items if i.kind is ItemKind.LETTER)


def _heads(c: Curriculum, *lesson_ids: str) -> dict[str, LessonItem]:
    return {lid: _head(c.lesson(lid)) for lid in lesson_ids}


def test_sheet_has_no_videos_and_keeps_listen(curriculum: Curriculum) -> None:
    """Решение автора 2026-10-25 (уточнение): в шпаргалке роликов нет — у всех букв 🔊."""
    heads = _heads(curriculum, "L003", "L004", "L005")
    s = screens.letters_sheet(
        curriculum, MIM, audio={h.id for h in heads.values()}, videos=_videos()
    )
    assert _watched(s.keyboard) == []
    assert sorted(_listen(s.keyboard)) == sorted(
        cb.Listen(item_id=h.id).pack() for h in heads.values()
    )


def test_full_sheet_keeps_keyboard_within_limits(curriculum: Curriculum) -> None:
    """28 🔊, ни одной 🎬: ряд ≤ ``SHEET_LISTEN_PER_ROW``, всего ≤ 100."""
    heads = {_head(les).id for les in curriculum.lessons if les.section == "letter"}
    s = screens.letters_sheet(curriculum, AFTER_LETTERS, audio=heads, videos=_videos())
    assert _watched(s.keyboard) == []
    assert len(_listen(s.keyboard)) == 28
    rows = s.keyboard.inline_keyboard
    assert all(len(row) <= screens.SHEET_LISTEN_PER_ROW for row in rows), [len(r) for r in rows]
    assert sum(len(row) for row in rows) <= 100  # Telegram: кнопок в клавиатуре

"""FR-62 (ADR-0079 п. 4 и «Дополнено 2026-11-01»): разметка клетками в Telegram через настоящие
обработчики, DI и SQLite.

Один экран: сверху слоги (аят суры — из curriculum/syllables/ayat.yaml через порт
``AyahSyllables``, иначе — буквы; ряд на слово, первый слог справа), под ними 11 видов по 2 в ряд
для выбранного слога, внизу действия («Чисто», «Готово», «Эталон», «Сам исправился»,
«Комментарий», «Плохая запись», «Читал не то», «Фонемы вручную», «Пропустить»). Нажал слог — он
выбран («[…]»); нажал вид — отметка в выбранном слоге («×»; несколько, повторное снимает); «!» —
здесь ошибку нашёл бот. «Буква» открывает шаг «какая прозвучала» и возвращает на один экран. В БД
пишут только «Готово» (с отметками) и «Чисто». Без смайликов в кнопках.

Кнопки ищутся по тексту (константы ``annotator_texts`` — их утверждает автор) и по полям
``AnnotateMark`` (``c`` — клетка, ``k`` — код вида, ``h`` — буква), а не по коду шага. Эталоны в
фонемах — выход quran-transcript с MOSHAF_PARAMS бота (tests/unit/test_arabic_text.py).
"""

import asyncio
import shutil
from collections.abc import AsyncIterator, Callable
from functools import cache
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
import yaml
from aiogram import Bot, Dispatcher
from aiogram.types import InlineKeyboardButton, User
from dishka import AsyncContainer
from dishka.integrations.aiogram import setup_dishka
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import muallim.domain.annotation as ann
from muallim.application.ports.storage import AudioStore
from muallim.application.use_cases.curriculum import PublishCurriculum
from muallim.bootstrap import di
from muallim.bootstrap.config import Settings
from muallim.bootstrap.di import create_container
from muallim.bootstrap.main import routers
from muallim.domain.assessment import assess
from muallim.domain.attempt import Attempt
from muallim.domain.curriculum import Curriculum, ItemKind
from muallim.domain.learner import Learner as LearnerRecord
from muallim.domain.phonetics import CONSONANTS
from muallim.domain.policy import GradingPolicy
from muallim.infrastructure.db.engine import create_engine
from muallim.infrastructure.db.repositories.attempts import SqlAttemptRepository
from muallim.infrastructure.db.repositories.learners import SqlLearnerRepository
from muallim.infrastructure.db.tables import annotations, metadata
from muallim.infrastructure.db.views import create_views
from muallim.presentation.telegram import annotator_texts as t
from muallim.presentation.telegram import callbacks
from muallim.presentation.telegram.callbacks import AnnotateAct
from muallim.research import annotators
from tests.fakes import FixedClock
from tests.integration.test_annotator_bot import VoiceTelegram, tap
from tests.integration.test_bot_flow import Learner

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
AYAT = ROOT / "curriculum" / "syllables" / "ayat.yaml"
ANNOTATOR_TG, STRANGER_TG = 900, 901

FATIHA_2 = "L097-03"  # ٱلْحَمْدُ لِلَّهِ رَبِّ ٱلْعَـٰلَمِينَ — 12 слогов, 4 слова
P = "ءَلحَمدُلِللَااهِرَببِلعَاالَمِۦۦن"  # её эталон (waqf)
SUB_AIN = P[:23] + "ء" + P[24:]  # бот услышал ء вместо ع в слоге «عَـٰ» (клетка 9)
NO_DAL = P[:6] + P[8:]  # без слога «دُ» (клетка 2)
L024_07 = "L024-07"  # مُحْسِنُ مَحْشَرُ مِنْحَرُ مَحْفَلُ أَحْسَنَ — не сура: по буквам
L024_07_PHONEMES = "مُحسِنُمَحشَرُمِنحَرُمَحفَلُءَحسَنَ"


@cache
def _ayat() -> dict[str, list[list[list[str]]]]:
    rows = yaml.safe_load(AYAT.read_text(encoding="utf-8"))["ayat"]
    return {r["text"]: r["words"] for r in rows}


def _settings(url: str, root: Path) -> Settings:
    return Settings(
        bot_token=SecretStr("1:test"),
        database_url=SecretStr(url),
        asr_backend="stub",
        audio_dir=root / "audio",
        reference_audio_dir=root / "reference",
        recitations_dir=root / "recitations",
        annotator_ids=f"A1:{ANNOTATOR_TG}",
    )


@pytest.fixture(scope="module")
def template(tmp_path_factory: pytest.TempPathFactory, curriculum: Curriculum) -> Path:
    """БД один раз на модуль: схема, опубликованная программа и ученик с согласием.

    Каждый тест берёт копию файла: публиковать программу заново на каждый тест — долго
    (тесты < 10 с, NFR-MNT-04).
    """
    path = tmp_path_factory.mktemp("annotation-marks") / "template.sqlite3"

    async def build() -> None:
        url = f"sqlite+aiosqlite:///{path}"
        engine = create_engine(url)
        async with engine.begin() as conn:
            await conn.run_sync(metadata.create_all)
            await conn.run_sync(create_views)
        await engine.dispose()
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(di, "load_curriculum", lambda *_: curriculum)
            container = create_container(_settings(url, path.parent))
            async with container() as request:
                await (await request.get(PublishCurriculum)).execute()
                session = await request.get(AsyncSession)
                learner = LearnerRecord(
                    UUID(int=1), 111, "L-aaaa", "ru", FixedClock().now(), research_consent=True
                )
                await SqlLearnerRepository(session).add(learner)
                await session.commit()
            await container.close()

    asyncio.run(build())
    return path


@pytest.fixture
async def app(
    tmp_path: Path, template: Path, curriculum: Curriculum, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[tuple[Dispatcher, AsyncContainer]]:
    db = tmp_path / "bot.sqlite3"
    shutil.copyfile(template, db)
    monkeypatch.setattr(di, "load_curriculum", lambda *_: curriculum)  # тот же course.ru.yaml
    container = create_container(_settings(f"sqlite+aiosqlite:///{db}", tmp_path))
    dp = Dispatcher()
    used = routers()
    dp.include_routers(*used)
    setup_dishka(container=container, router=dp, auto_inject=True)
    await dp.emit_startup()
    try:
        yield dp, container
    finally:
        await dp.emit_shutdown()
        await container.close()
        for r in used:
            dp.sub_routers.remove(r)
            r._parent_router = None


Seed = Callable[..., Any]


@pytest.fixture
def seed(app: tuple[Dispatcher, AsyncContainer]) -> Seed:
    """Попытка ученика с согласием (по умолчанию 20): пункт программы, эталон и что услышал бот."""
    _, container = app

    async def add(item_id: str, reference: str, heard: str, n: int = 20) -> str:
        async with container() as request:
            session, store = await request.get(AsyncSession), await request.get(AudioStore)
            curriculum = await request.get(Curriculum)
            sha = await store.save(b"OggS-learner-voice-%d" % n)
            result = assess(reference, heard)
            await SqlAttemptRepository(session).add(
                Attempt(UUID(int=n), UUID(int=1), item_id, curriculum.version, "muaalem",
                        result, GradingPolicy().verdict(result), sha, 900, 10,
                        FixedClock().now()),
                tuple("msg" for _ in result.errors),
            )  # fmt: skip
            await session.commit()
            return curriculum.item(item_id).text

    return add


@pytest.fixture
def person(app: tuple[Dispatcher, AsyncContainer]) -> Callable[[int], Learner]:
    dp, _ = app

    def make(telegram_id: int) -> Learner:
        tg = VoiceTelegram()
        user = User(id=telegram_id, is_bot=False, first_name="Учитель", language_code="ru")
        return Learner(dp, Bot("1:test", session=tg), tg, user)

    return make


async def _rows(container: AsyncContainer, table: Any) -> list[dict[str, Any]]:
    async with container() as request:
        session = await request.get(AsyncSession)
        return [dict(r) for r in (await session.execute(select(table))).mappings().all()]


async def _marks(container: AsyncContainer) -> list[dict[str, Any]]:
    from muallim.infrastructure.db.tables import annotation_marks  # noqa: PLC0415

    return await _rows(container, annotation_marks)


# ---------- кнопки на экране ----------
def _keyboard(person: Learner) -> list[list[InlineKeyboardButton]]:
    markup = person.last_screen().reply_markup
    assert markup is not None
    return markup.inline_keyboard


def _screen_text(person: Learner) -> str:
    screen = person.last_screen()
    return screen.text or screen.caption or ""


def _mark_buttons(person: Learner) -> list[tuple[InlineKeyboardButton, Any]]:
    """Кнопки разметки клетками (``AnnotateMark``) с разобранными полями."""
    mark = callbacks.AnnotateMark
    prefix = mark.__prefix__ + ":"
    return [
        (b, mark.unpack(b.callback_data))
        for row in _keyboard(person)
        for b in row
        if b.callback_data and b.callback_data.startswith(prefix)
    ]


def _is_cell(b: InlineKeyboardButton, data: Any, pieces: list[str]) -> bool:
    """Кнопка слога несёт свой кусочек; кнопки видов — русские слова, кусочков в них нет."""
    return 0 <= data.c < len(pieces) and pieces[data.c] in b.text


def _cell_rows(person: Learner, pieces: list[str]) -> list[list[int]]:
    """Ряды слогов: номера клеток по порядку кнопок в ряду."""
    mark = callbacks.AnnotateMark
    out = []
    for row in _keyboard(person):
        cells = [
            mark.unpack(b.callback_data or "").c
            for b in row
            if (b.callback_data or "").startswith(mark.__prefix__ + ":")
            and _is_cell(b, mark.unpack(b.callback_data or ""), pieces)
        ]
        if cells:
            out.append(cells)
    return out


def _cell_button(person: Learner, n: int, piece: str) -> InlineKeyboardButton:
    for b, data in _mark_buttons(person):
        if data.c == n and piece in b.text:
            return b
    raise AssertionError(f"на экране нет слога {n} «{piece}»")


def _cell(person: Learner, n: int, piece: str) -> str:
    return str(_cell_button(person, n, piece).callback_data)


def _kind_buttons(person: Learner) -> dict[str, InlineKeyboardButton]:
    codes = {k.code: str(k) for k in ann.MarkKind}
    return {codes[d.k]: b for b, d in _mark_buttons(person) if d.k in codes}


def _kind(person: Learner, kind: str) -> str:
    found = _kind_buttons(person).get(kind)
    assert found is not None, f"на экране нет вида {kind}"
    return str(found.callback_data)


def _letter(person: Learner, phoneme: str) -> str:
    for b, data in _mark_buttons(person):
        if data.h == phoneme:
            return str(b.callback_data)
    raise AssertionError(f"на экране нет буквы {phoneme}")


def _texts(person: Learner) -> list[str]:
    return [b.text for row in _keyboard(person) for b in row]


def _on_one_screen(person: Learner) -> None:
    """После шага «буква» — снова один экран (слоги, виды, действия)."""
    assert t.BTN_DONE in _texts(person) and t.BTN_CLEAN in _texts(person)


def _pieces(text: str) -> list[str]:
    return [piece for word in _ayat()[text] for piece, _ in word]


def _letter_pieces(text: str) -> list[str]:
    return [c.piece for c in ann.annotation_cells(text, None)]


async def _open(person: Learner) -> None:
    """Один экран (ADR-0079, дополнено 2026-11-01): слоги, виды и действия — сразу."""
    await person.write("/annotate")


# Эмодзи: всё вне BMP, знак варианта U+FE0F и блоки, где живут ⌚⏩⏹☀⚠✅✏❌➕ и т. п.
# «×», «!», «[]» и «✓» (U+2713, не Emoji_Presentation) — разрешены.
_EMOJI_BLOCKS = ((0x231A, 0x231B), (0x23E9, 0x23FA), (0x2600, 0x27BF), (0x2B00, 0x2BFF))


def _has_emoji(text: str) -> bool:
    for ch in text:
        code = ord(ch)
        if code > 0xFFFF or code == 0xFE0F:
            return True
        if ch != "✓" and any(lo <= code <= hi for lo, hi in _EMOJI_BLOCKS):
            return True
    return False


def test_annotator_buttons_use_the_words_approved_by_the_author() -> None:
    """Дополнено 2026-11-01, п. 2: короткие слова без смайликов (решение автора)."""
    assert (
        t.BTN_CLEAN, t.BTN_DONE, t.BTN_REF, t.BTN_SELF, t.BTN_COMMENT, t.BTN_BAD, t.BTN_OFF,
        t.BTN_MANUAL, t.BTN_SKIP,
    ) == (
        "Чисто", "Готово", "Эталон", "Сам исправился", "Комментарий", "Плохая запись",
        "Читал не то", "Фонемы вручную", "Пропустить",
    )  # fmt: skip
    assert t.KIND_BUTTONS == {
        "letter": "Буква", "vowel": "Огласовка", "madd": "Длина", "shadda_sukun": "Шадда/сукун",
        "missing": "Пропуск", "extra": "Лишний звук", "tafkhim": "Твёрдость", "ghunna": "Гунна",
        "qalqala": "Калькаля", "halting": "Запинка", "wrong_stop": "Пауза не там",
    }  # fmt: skip


# ---------- один экран ----------
async def test_one_screen_has_syllables_kinds_and_actions_without_emoji(
    tmp_path: Path, seed: Seed, person: Callable[[int], Learner]
) -> None:
    """Сверху слоги (ряд на слово, первый справа), под ними 11 видов по 2 в ряд, внизу действия."""
    (tmp_path / "reference").mkdir()
    (tmp_path / "reference" / f"{FATIHA_2}.ogg").write_bytes(b"OggS-teacher")
    text = await seed(FATIHA_2, P, SUB_AIN)
    pieces = _pieces(text)
    teacher = person(ANNOTATOR_TG)
    await _open(teacher)
    assert text in "\n".join(teacher.tg.texts())  # карточка: строка урока
    await teacher.press(_cell(teacher, 0, pieces[0]))
    assert _cell_rows(teacher, pieces) == [[2, 1, 0], [5, 4, 3], [7, 6], [11, 10, 9, 8]]
    rows = _keyboard(teacher)
    kinds = {b.callback_data for b in _kind_buttons(teacher).values()}
    kind_rows = [r for r in rows if any(b.callback_data in kinds for b in r)]
    assert len(kinds) == 11 and len(kind_rows) == 6
    assert all(len(r) <= 2 and all(b.callback_data in kinds for b in r) for r in kind_rows)
    mark = callbacks.AnnotateMark
    cell_rows = [
        i for i, r in enumerate(rows)
        if any((b.callback_data or "").startswith(mark.__prefix__ + ":")
               and _is_cell(b, mark.unpack(b.callback_data or ""), pieces) for b in r)
    ]  # fmt: skip
    first_kind_row = rows.index(kind_rows[0])
    assert cell_rows and all(i < first_kind_row for i in cell_rows)  # слоги выше видов
    texts = _texts(teacher)
    for button in (
        t.BTN_CLEAN, t.BTN_DONE, t.BTN_REF, t.BTN_SELF, t.BTN_COMMENT, t.BTN_BAD, t.BTN_OFF,
        t.BTN_MANUAL, t.BTN_SKIP,
    ):  # fmt: skip
        assert button in texts, button
    emoji = [x for x in texts if _has_emoji(x)]
    assert not emoji, emoji


async def test_bot_cell_has_exclamation_and_selected_cell_is_in_brackets(
    seed: Seed, person: Callable[[int], Learner]
) -> None:
    text = await seed(FATIHA_2, P, SUB_AIN)
    pieces = _pieces(text)
    teacher = person(ANNOTATOR_TG)
    await _open(teacher)
    bot = [d.c for b, d in _mark_buttons(teacher) if _is_cell(b, d, pieces) and "!" in b.text]
    assert bot == [9]  # «!» — только где ошибку нашёл бот
    await teacher.press(_cell(teacher, 5, pieces[5]))
    selected = _cell_button(teacher, 5, pieces[5]).text
    assert "[" in selected and "]" in selected
    await teacher.press(_cell(teacher, 2, pieces[2]))  # другой слог — выбран он
    assert "[" in _cell_button(teacher, 2, pieces[2]).text
    assert "[" not in _cell_button(teacher, 5, pieces[5]).text


async def test_first_screen_names_the_syllable_where_bot_found_an_error(
    seed: Seed, person: Callable[[int], Learner]
) -> None:
    """Подсказку бота показывать (решение автора): кусочек назван не только в строке урока."""
    text = await seed(FATIHA_2, P, SUB_AIN)
    teacher = person(ANNOTATOR_TG)
    await _open(teacher)
    beside_line = "\n".join(teacher.tg.texts()).replace(text, "")
    assert _pieces(text)[9] in beside_line


async def test_first_screen_says_bot_found_nothing(
    seed: Seed, person: Callable[[int], Learner]
) -> None:
    await seed(FATIHA_2, P, P)
    teacher = person(ANNOTATOR_TG)
    await _open(teacher)
    assert "не нашёл" in "\n".join(teacher.tg.texts())
    assert t.BTN_CLEAN in _texts(teacher)


async def test_clean_reading_when_bot_found_nothing_is_agree(
    app: tuple[Dispatcher, AsyncContainer], seed: Seed, person: Callable[[int], Learner]
) -> None:
    _, container = app
    await seed(FATIHA_2, P, P)
    teacher = person(ANNOTATOR_TG)
    await _open(teacher)
    await teacher.press(tap(teacher, t.BTN_CLEAN))
    (label,) = await _rows(container, annotations)
    assert (label["label"], label["corrected_phonemes"], label["entry"]) == ("agree", P, "cells")
    assert await _marks(container) == []


async def test_clean_reading_when_bot_found_an_error_is_fix_with_reference(
    app: tuple[Dispatcher, AsyncContainer], seed: Seed, person: Callable[[int], Learner]
) -> None:
    _, container = app
    await seed(FATIHA_2, P, SUB_AIN)
    teacher = person(ANNOTATOR_TG)
    await _open(teacher)
    await teacher.press(tap(teacher, t.BTN_CLEAN))
    (label,) = await _rows(container, annotations)
    assert (label["label"], label["corrected_phonemes"], label["entry"]) == ("fix", P, "cells")
    assert await _marks(container) == []


async def test_line_outside_suras_is_split_into_letter_cells(
    seed: Seed, person: Callable[[int], Learner]
) -> None:
    text = await seed(L024_07, L024_07_PHONEMES, L024_07_PHONEMES)
    pieces = _letter_pieces(text)
    teacher = person(ANNOTATOR_TG)
    await _open(teacher)
    rows = _cell_rows(teacher, pieces)
    assert sorted(n for row in rows for n in row) == list(range(len(pieces)))
    assert len(rows) == len(text.split())  # ряд на слово
    assert not [b for b, d in _mark_buttons(teacher) if _is_cell(b, d, pieces) and "!" in b.text]


# ---------- слог → вид (→ буква) → «Готово» ----------
async def test_letter_mark_like_bot_is_saved_as_agree_with_its_cell(
    app: tuple[Dispatcher, AsyncContainer], seed: Seed, person: Callable[[int], Learner]
) -> None:
    """Учитель слышит в «عَـٰ» хамзу — как бот: согласие считается само, фонемы выводятся."""
    _, container = app
    text = await seed(FATIHA_2, P, SUB_AIN)
    piece = _pieces(text)[9]
    teacher = person(ANNOTATOR_TG)
    await _open(teacher)
    await teacher.press(_cell(teacher, 9, piece))
    await teacher.press(_kind(teacher, "letter"))
    await teacher.press(_letter(teacher, "ء"))  # что услышал бот в этой клетке — среди вариантов
    _on_one_screen(teacher)
    assert "×" in _cell_button(teacher, 9, piece).text
    assert t.KIND_BUTTONS["letter"].lower() in _screen_text(teacher).lower()  # «отмечено: …»
    await teacher.press(tap(teacher, t.BTN_DONE))

    (label,) = await _rows(container, annotations)
    assert (label["label"], label["corrected_phonemes"], label["entry"]) == (
        "agree", SUB_AIN, "cells",
    )  # fmt: skip
    assert label["source"] == "telegram" and label["seconds_spent"] is not None
    (mark,) = await _marks(container)
    assert (mark["annotation_id"], mark["cell"], mark["layout"], mark["kind"]) == (
        label["id"], 9, "syllables", "letter",
    )  # fmt: skip
    assert (mark["piece"], text[mark["char_start"] : mark["char_end"]]) == (piece, piece)
    assert (mark["heard_letter"], mark["bot_flagged"]) == ("ء", True)


async def test_missing_syllable_is_saved_with_phonemes_without_it(
    app: tuple[Dispatcher, AsyncContainer], seed: Seed, person: Callable[[int], Learner]
) -> None:
    """«Пропуск» = не прочитана вся клетка; бот ничего не нашёл — значит ``fix``."""
    _, container = app
    text = await seed(FATIHA_2, P, P)
    teacher = person(ANNOTATOR_TG)
    await _open(teacher)
    await teacher.press(_cell(teacher, 2, _pieces(text)[2]))
    await teacher.press(_kind(teacher, "missing"))
    await teacher.press(tap(teacher, t.BTN_DONE))
    (label,) = await _rows(container, annotations)
    assert (label["label"], label["corrected_phonemes"]) == ("fix", NO_DAL)
    assert [(m["cell"], m["kind"], m["bot_flagged"]) for m in await _marks(container)] == [
        (2, "missing", False)
    ]


async def test_several_kinds_and_second_press_removes_exactly_that_kind(
    app: tuple[Dispatcher, AsyncContainer], seed: Seed, person: Callable[[int], Learner]
) -> None:
    """В слоге несколько видов; повторное нажатие снимает именно этот вид. Текст над кнопками
    называет выбранный слог и отмеченное."""
    _, container = app
    text = await seed(FATIHA_2, P, P)
    pieces = _pieces(text)
    teacher = person(ANNOTATOR_TG)
    await _open(teacher)
    await teacher.press(_cell(teacher, 5, pieces[5]))
    for kind in ("vowel", "tafkhim", "madd", "madd"):  # мадд нажат дважды — снят
        await teacher.press(_kind(teacher, kind))
    screen = _screen_text(teacher).lower()
    for kind in ("vowel", "tafkhim"):
        assert t.KIND_BUTTONS[kind].lower() in screen
    assert t.KIND_BUTTONS["madd"].lower() not in screen
    await teacher.press(_cell(teacher, 3, pieces[3]))  # другой слог: отметки 5 на месте
    await teacher.press(_kind(teacher, "halting"))
    await teacher.press(tap(teacher, t.BTN_DONE))
    (label,) = await _rows(container, annotations)
    assert (label["label"], label["corrected_phonemes"]) == ("fix", None)  # не сводится к фонемам
    assert sorted((m["cell"], m["kind"]) for m in await _marks(container)) == [
        (3, "halting"), (5, "tafkhim"), (5, "vowel"),
    ]  # fmt: skip


async def test_done_without_marks_hints_and_saves_nothing(
    app: tuple[Dispatcher, AsyncContainer], seed: Seed, person: Callable[[int], Learner]
) -> None:
    """«Готово» без отметок — подсказка «Отметьте слог или нажмите «Чисто»»; ничего не пишется.
    Отметки, снятые повторным нажатием, — тоже «без отметок»."""
    _, container = app
    text = await seed(FATIHA_2, P, P)
    teacher = person(ANNOTATOR_TG)
    await _open(teacher)
    for unmark in (False, True):
        before = len(teacher.tg.texts())
        if unmark:
            await teacher.press(_cell(teacher, 3, _pieces(text)[3]))
            await teacher.press(_kind(teacher, "vowel"))
            await teacher.press(_kind(teacher, "vowel"))
        await teacher.press(tap(teacher, t.BTN_DONE))
        hints = teacher.tg.alerts() + teacher.tg.texts()[before:]
        assert any(t.BTN_CLEAN in h for h in hints), hints  # «…или нажмите «Чисто»»
    assert await _rows(container, annotations) == [] and await _marks(container) == []


async def test_comment_is_saved_with_the_next_answer(
    app: tuple[Dispatcher, AsyncContainer], seed: Seed, person: Callable[[int], Learner]
) -> None:
    """«Комментарий» → разметчик пишет текст → он уходит в ``annotations.comment`` вместе со
    следующим ответом на эту запись («Чисто» или «Готово»)."""
    _, container = app
    await seed(FATIHA_2, P, P)
    teacher = person(ANNOTATOR_TG)
    await _open(teacher)
    await teacher.press(tap(teacher, t.BTN_COMMENT))
    await teacher.write("сомневаюсь, шум в конце")
    assert await _rows(container, annotations) == []  # комментарий сам по себе — не метка
    await teacher.press(tap(teacher, t.BTN_CLEAN))
    (label,) = await _rows(container, annotations)
    assert (label["label"], label["comment"]) == ("agree", "сомневаюсь, шум в конце")


async def test_dont_know_saves_letter_mark_without_heard_letter(
    app: tuple[Dispatcher, AsyncContainer], seed: Seed, person: Callable[[int], Learner]
) -> None:
    """Шаг «буква»: среди вариантов — пара из ``pair_tips`` (ه ↔ ح); «не знаю» → NULL."""
    _, container = app
    text = await seed(FATIHA_2, P, P)
    teacher = person(ANNOTATOR_TG)
    await _open(teacher)
    await teacher.press(_cell(teacher, 5, _pieces(text)[5]))  # «هِ»
    await teacher.press(_kind(teacher, "letter"))
    assert _letter(teacher, "ح")  # пара حه из curriculum/lexicon.ru.yaml
    await teacher.press(tap(teacher, t.BTN_DONT_KNOW))
    _on_one_screen(teacher)
    await teacher.press(tap(teacher, t.BTN_DONE))
    (label,) = await _rows(container, annotations)
    assert (label["label"], label["corrected_phonemes"]) == ("fix", None)
    assert [(m["cell"], m["kind"], m["heard_letter"]) for m in await _marks(container)] == [
        (5, "letter", None)
    ]


# ---------- черновик, повторы, права ----------
async def test_new_annotate_discards_the_draft(
    app: tuple[Dispatcher, AsyncContainer], seed: Seed, person: Callable[[int], Learner]
) -> None:
    """Новый заход /annotate (как прежние «Отмена»/«Закончить») — черновик сброшен."""
    _, container = app
    text = await seed(FATIHA_2, P, SUB_AIN)
    pieces = _pieces(text)
    teacher = person(ANNOTATOR_TG)
    await _open(teacher)
    await teacher.press(_cell(teacher, 9, pieces[9]))
    await teacher.press(_kind(teacher, "vowel"))
    await _open(teacher)
    assert not [b for b, d in _mark_buttons(teacher) if _is_cell(b, d, pieces) and "×" in b.text]
    assert await _rows(container, annotations) == []


async def test_skip_discards_the_draft(
    app: tuple[Dispatcher, AsyncContainer], seed: Seed, person: Callable[[int], Learner]
) -> None:
    """«Пропустить» ничего не пишет; вернувшись к записи, отметок нет."""
    _, container = app
    text = await seed(FATIHA_2, P, SUB_AIN)
    pieces = _pieces(text)
    teacher = person(ANNOTATOR_TG)
    await _open(teacher)
    await teacher.press(_cell(teacher, 9, pieces[9]))
    await teacher.press(_kind(teacher, "vowel"))
    await teacher.press(tap(teacher, t.BTN_SKIP))
    assert await _rows(container, annotations) == []
    await _open(teacher)  # новый заход: пропущенная снова в очереди
    assert not [b for b, d in _mark_buttons(teacher) if _is_cell(b, d, pieces) and "×" in b.text]


async def test_drafts_of_two_records_do_not_mix_after_redo(
    app: tuple[Dispatcher, AsyncContainer], seed: Seed, person: Callable[[int], Learner]
) -> None:
    """Черновик — свой у каждой записи: «Переделать» прошлой не берёт отметки текущей."""
    _, container = app
    text = await seed(FATIHA_2, P, SUB_AIN, n=20)  # бот нашёл ошибку — в очереди первая
    await seed(FATIHA_2, P, P, n=21)
    pieces = _pieces(text)
    teacher = person(ANNOTATOR_TG)
    await _open(teacher)
    await teacher.press(tap(teacher, t.BTN_CLEAN))  # 20 — чисто; на экране 21
    await teacher.press(_cell(teacher, 2, pieces[2]))
    await teacher.press(_kind(teacher, "missing"))
    done_21 = tap(teacher, t.BTN_DONE)
    await teacher.press(AnnotateAct(a=UUID(int=20).hex, act="redo").pack())
    assert not [b for b, d in _mark_buttons(teacher) if _is_cell(b, d, pieces) and "×" in b.text]
    await teacher.press(_cell(teacher, 9, pieces[9]))
    await teacher.press(_kind(teacher, "letter"))
    await teacher.press(_letter(teacher, "ء"))
    await teacher.press(tap(teacher, t.BTN_DONE))
    await teacher.press(done_21)  # черновик 21 дожил до своего «Готово»

    labels = await _rows(container, annotations)
    assert [(lb["attempt_id"], lb["label"], lb["corrected_phonemes"]) for lb in labels] == [
        (UUID(int=20), "fix", P), (UUID(int=20), "agree", SUB_AIN), (UUID(int=21), "fix", NO_DAL),
    ]  # fmt: skip
    by_label = {lb["id"]: lb["attempt_id"] for lb in labels}
    marks = sorted(
        (by_label[m["annotation_id"]].int, m["cell"], m["kind"]) for m in await _marks(container)
    )
    assert marks == [(20, 9, "letter"), (21, 2, "missing")]


async def test_second_done_and_old_cell_button_save_nothing_more(
    app: tuple[Dispatcher, AsyncContainer], seed: Seed, person: Callable[[int], Learner]
) -> None:
    """Двойное «Готово» и кнопка слога после «Готово» — второй метки нет."""
    _, container = app
    text = await seed(FATIHA_2, P, P)
    pieces = _pieces(text)
    teacher = person(ANNOTATOR_TG)
    await _open(teacher)
    old_cell = _cell(teacher, 3, pieces[3])
    await teacher.press(_cell(teacher, 2, pieces[2]))
    await teacher.press(_kind(teacher, "missing"))
    done = tap(teacher, t.BTN_DONE)
    await teacher.press(done)
    await teacher.press(done)
    await teacher.press(old_cell)
    assert len(await _rows(container, annotations)) == 1
    assert len(await _marks(container)) == 1


async def test_manual_entry_keeps_the_phoneme_input(
    app: tuple[Dispatcher, AsyncContainer], seed: Seed, person: Callable[[int], Learner]
) -> None:
    _, container = app
    await seed(FATIHA_2, P, SUB_AIN)
    teacher = person(ANNOTATOR_TG)
    await _open(teacher)
    await teacher.press(tap(teacher, t.BTN_MANUAL))
    await teacher.write(NO_DAL)
    (label,) = await _rows(container, annotations)
    assert (label["label"], label["corrected_phonemes"], label["entry"]) == (
        "fix", NO_DAL, "phonemes",
    )  # fmt: skip
    assert await _marks(container) == []


async def test_mark_buttons_of_stranger_or_unknown_attempt_do_nothing(
    app: tuple[Dispatcher, AsyncContainer], seed: Seed, person: Callable[[int], Learner]
) -> None:
    """Подделанная или старая кнопка — молча ничего: ни метки, ни клеток, ни сообщений."""
    _, container = app
    text = await seed(FATIHA_2, P, SUB_AIN)
    teacher = person(ANNOTATOR_TG)
    await _open(teacher)
    pressed = _cell(teacher, 9, _pieces(text)[9])
    stranger = person(STRANGER_TG)
    await stranger.write("/start")
    shown = len(stranger.tg.shown)
    for button, _ in _mark_buttons(teacher):
        await stranger.press(str(button.callback_data))
    await stranger.press(tap(teacher, t.BTN_DONE))
    await stranger.press(tap(teacher, t.BTN_CLEAN))
    assert len(stranger.tg.shown) == shown and stranger.tg.alerts() == []  # молча
    gone = callbacks.AnnotateMark.unpack(pressed)
    await teacher.press(gone.model_copy(update={"a": UUID(int=99).hex}).pack())
    assert await _rows(container, annotations) == [] and await _marks(container) == []


async def test_revoked_teacher_cannot_save_cells(
    app: tuple[Dispatcher, AsyncContainer], seed: Seed, person: Callable[[int], Learner]
) -> None:
    """Доступ отозвали посреди разметки: «слог → вид → Готово» ничего не сохраняет."""
    _, container = app
    text = await seed(FATIHA_2, P, SUB_AIN)
    teacher = person(ANNOTATOR_TG)
    await _open(teacher)
    done = tap(teacher, t.BTN_DONE)
    await teacher.press(_cell(teacher, 9, _pieces(text)[9]))
    await teacher.press(_kind(teacher, "vowel"))
    async with container() as request:
        session = await request.get(AsyncSession)
        await annotators.revoke(session, "A1", FixedClock())
        await session.commit()
    await teacher.press(done)
    assert await _rows(container, annotations) == [] and await _marks(container) == []


# ---------- ограничения Telegram на самых длинных строках программы ----------
def _longest(curriculum: Curriculum, *, syllables: bool) -> str:
    ayat = _ayat()

    def size(text: str) -> int:
        return len(_pieces(text)) if syllables else len(_letter_pieces(text))

    items = [
        i
        for les in curriculum.lessons
        for i in les.items
        if i.kind is not ItemKind.RULE and (i.text in ayat) is syllables
    ]
    return max(items, key=lambda i: size(i.text)).id


def _fits_telegram(person: Learner) -> None:
    rows = _keyboard(person)
    assert sum(len(r) for r in rows) <= 100
    assert all(len(r) <= 8 for r in rows)
    assert all(len((b.callback_data or "").encode()) <= 64 for r in rows for b in r)
    emoji = [b.text for r in rows for b in r if _has_emoji(b.text)]
    assert not emoji, emoji


@pytest.mark.parametrize("syllables", [True, False], ids=["longest-ayah", "longest-letters"])
async def test_keyboards_of_the_longest_line_fit_telegram_limits(
    curriculum: Curriculum, seed: Seed, person: Callable[[int], Learner], syllables: bool
) -> None:
    """≤ 100 кнопок, ≤ 8 в ряду, ``callback_data`` ≤ 64 байт, без эмодзи — на каждом шаге."""
    item = _longest(curriculum, syllables=syllables)
    text = curriculum.item(item).text
    reference = text.replace(" ", "")  # фонемы здесь не важны: проверяется размер клавиатуры
    await seed(item, reference, reference)
    pieces = _pieces(text) if syllables else _letter_pieces(text)
    teacher = person(ANNOTATOR_TG)
    await _open(teacher)
    _fits_telegram(teacher)
    last = len(pieces) - 1
    await teacher.press(_cell(teacher, last, pieces[last]))
    _fits_telegram(teacher)  # один экран: слоги + виды + действия
    assert sorted(n for row in _cell_rows(teacher, pieces) for n in row) == list(range(len(pieces)))
    assert len(_kind_buttons(teacher)) == 11
    await teacher.press(_kind(teacher, "letter"))
    _fits_telegram(teacher)  # шаг «буква»
    assert t.BTN_DONT_KNOW in _texts(teacher)
    await teacher.press(tap(teacher, t.BTN_OTHER_LETTER))  # «другая…» — все 28 букв
    _fits_telegram(teacher)
    assert {d.h for _, d in _mark_buttons(teacher)} >= set(CONSONANTS)


def test_longest_mark_callback_fits_64_bytes() -> None:
    data = callbacks.AnnotateMark(a=UUID(int=2**128 - 1).hex, s="h", c=99, k="sss", h="ض")
    assert len(data.pack().encode()) <= 64

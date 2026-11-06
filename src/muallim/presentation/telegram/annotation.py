"""Разметка в Telegram (FR-17, ADR-0041, ADR-0072): /annotate, кнопки разметчика, исправление фонем.

Вход открыт: кто написал /annotate, получает код и сразу размечает (решение автора 2026-10-24).
Отозванному /annotate уходит обычному обработчику ученика (SkipHandler); кнопки того, кто не
входил или отозван, молча ничего не делают — права проверяет сценарий при каждом действии.
Записи учеников отправляются с protect_content: их нельзя переслать или сохранить. Только личный
чат. Роутер подключается раньше роутера ученика (bootstrap/main.py: ``routers()``).

FR-62 (ADR-0079, дополнено 2026-11-01): один экран — сверху слоги (ряд на слово, первый справа),
под ними шесть главных видов для выбранного слога и «Ещё» (прочие шесть), внизу действия.
Учитель оценивает чтение ученика: «Бот прав» (ответ бота), «Чисто», «Исправить» (отметки бота — в
черновик) или свои отметки и «Готово»; у «Буква», «Огласовка», «Сукун», «Лишний звук», «Пропуск» —
вопрос «что прозвучало» (FR-63, ADR-0080). Текст и клавиатура меняются на месте; черновик отметок —
в FSM (``Desk``), в БД пишут только «Готово», «Бот прав» и «Чисто».
"""

import time
from contextlib import suppress
from dataclasses import dataclass
from html import escape
from typing import Final
from uuid import UUID

from aiogram import Bot, F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dishka import FromDishka

from muallim.application.ports.storage import ReferenceAudioLibrary
from muallim.application.use_cases.annotation import (
    AnnotatorAccess,
    JoinAnnotation,
    NextAnnotation,
    NotAnnotator,
    RedeemInvite,
    RedeemResult,
    ShownTask,
    SubmitAnnotation,
    SubmitMarks,
)
from muallim.domain.annotation import (
    MAIN_KINDS,
    MORE_KINDS,
    NO_VOWEL,
    AnnotationStatus,
    AnnotationTask,
    LabelError,
    Mark,
    MarkKind,
    bot_letters,
    cell_sounds,
    check_marks,
    looks_like_invite,
    marks_from_bot,
    pair_letters,
    written_letters,
)
from muallim.domain.curriculum import Curriculum
from muallim.domain.learner import Learner
from muallim.presentation.telegram import annotator_texts as t
from muallim.presentation.telegram.callbacks import AnnotateAct, AnnotateMark
from muallim.presentation.telegram.render import in_word

router: Final = Router(name="annotator")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")

MAX_ROW: Final = 8  # кнопок в ряду inline-клавиатуры Telegram
KINDS_ROW: Final = 2  # видов в ряду (решение автора 2026-11-01)
ACTIONS_ROW: Final = 2
LETTER_ROW: Final = 7
ALPHABET: Final = "ءبتثجحخدذرزسشصضطظعغفقكلمنهوي"  # 28 согласных фонетического алфавита по порядку


def _set(value: object) -> set[str]:
    return {str(v) for v in value} if isinstance(value, list) else set()


def _map(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


@dataclass(frozen=True, slots=True)
class Desk:
    """Что разметчик делает сейчас — в FSM aiogram, свой у каждого чата и диспетчера.

    Хранится только JSON-совместимое (hex попыток, секунды, тексты карточек). Время показа — по
    ``time.monotonic``, как до ADR-0049: при постоянном хранилище FSM (TD-FN-70) перейти на часы с
    защитой от отрицательных значений. Не данные исследования: ответ — в БД.
    """

    state: FSMContext

    async def _get(self, key: str) -> object:
        return (await self.state.get_data()).get(key)

    async def _put(self, key: str, attempt: UUID, value: object | None) -> None:
        """Значение по попытке в словаре ``key``; None — убрать."""
        stored = _map(await self._get(key))
        if value is None:
            stored.pop(attempt.hex, None)
        else:
            stored[attempt.hex] = value
        await self.state.update_data({key: stored})

    async def _flag(self, key: str, attempt: UUID, *, on: bool) -> None:
        marked = _set(await self._get(key))
        marked = marked | {attempt.hex} if on else marked - {attempt.hex}
        await self.state.update_data({key: sorted(marked)})

    async def fixing(self) -> UUID | None:
        """Попытка, для которой ждём фонемы текстом («Фонемы вручную»)."""
        value = await self._get("fixing")
        return UUID(hex=value) if isinstance(value, str) else None

    async def set_fixing(self, attempt: UUID | None) -> None:
        await self.state.update_data(
            {"fixing": attempt.hex if attempt else None, "commenting": None}
        )

    async def commenting(self) -> UUID | None:
        """Попытка, для которой ждём комментарий текстом."""
        value = await self._get("commenting")
        return UUID(hex=value) if isinstance(value, str) else None

    async def set_commenting(self, attempt: UUID | None) -> None:
        await self.state.update_data(
            {"commenting": attempt.hex if attempt else None, "fixing": None}
        )

    async def comment(self, attempt: UUID) -> str:
        value = _map(await self._get("comments")).get(attempt.hex)
        return value if isinstance(value, str) else ""

    async def set_comment(self, attempt: UUID, text: str | None) -> None:
        await self._put("comments", attempt, text)

    async def skipped(self) -> frozenset[UUID]:
        """Пропущенные в этот заход — не показывать снова."""
        return frozenset(UUID(hex=h) for h in _set(await self._get("skipped")))

    async def skip(self, attempt: UUID) -> None:
        await self._flag("skipped", attempt, on=True)

    async def self_corrected(self, attempt: UUID) -> bool:
        return attempt.hex in _set(await self._get("self_corrected"))

    async def toggle_self_corrected(self, attempt: UUID) -> bool:
        """«Сам исправился» — переключатель до ответа; возвращает новое значение."""
        on = not await self.self_corrected(attempt)
        await self._flag("self_corrected", attempt, on=on)
        return on

    async def shown(self, attempt: UUID, *, keep: bool = False) -> None:
        """Когда показана запись — для времени ответа; ``keep`` — не сбрасывать уже отмеченное."""
        times = _map(await self._get("shown_at"))
        if not (keep and attempt.hex in times):
            times[attempt.hex] = time.monotonic()
        await self.state.update_data({"shown_at": times})

    async def seconds(self, attempt: UUID) -> int | None:
        """Сколько секунд разметчик думал над записью; отметка снимается."""
        times = _map(await self._get("shown_at"))
        started = times.pop(attempt.hex, None)
        await self.state.update_data({"shown_at": times})
        return round(time.monotonic() - started) if isinstance(started, float | int) else None

    async def redoing(self, attempt: UUID) -> None:
        """«Переделать»: эта запись показана снова поверх текущей."""
        await self._flag("redo", attempt, on=True)

    async def done_redo(self, attempt: UUID) -> bool:
        """Ответ был на повторно показанную запись — тогда следующую не присылать: текущая
        карточка уже на экране выше (иначе одна запись придёт дважды)."""
        if attempt.hex not in _set(await self._get("redo")):
            return False
        await self._flag("redo", attempt, on=False)
        return True

    async def start_over(self) -> None:
        """Новый заход /annotate: не ждём текста, пропущенные снова доступны, черновиков нет."""
        await self.state.update_data({
            "fixing": None, "commenting": None, "skipped": [], "redo": [], "marks": {},
            "marking": [], "selected": {}, "cards": {}, "comments": {}, "panels": {},
        })  # fmt: skip

    async def open(self, attempt: UUID, card: str, selected: int) -> None:
        """Запись на экране: текст карточки, выбранный слог; черновик — с нуля."""
        await self._flag("marking", attempt, on=True)
        await self._put("cards", attempt, card)
        await self.set_panel(attempt, "main")
        await self.select(attempt, selected)
        await self.set_draft(attempt, [])

    async def marking(self, attempt: UUID) -> bool:
        """Запись на экране и ещё не сохранена: её кнопки действуют."""
        return attempt.hex in _set(await self._get("marking"))

    async def close(self, attempt: UUID) -> None:
        """Сохранено или пропущено: кнопки записи больше не действуют, черновик сброшен."""
        await self._flag("marking", attempt, on=False)
        await self.set_draft(attempt, [])
        await self._flag("self_corrected", attempt, on=False)
        for key in ("cards", "selected", "comments", "panels"):
            await self._put(key, attempt, None)

    async def panel(self, attempt: UUID) -> str:
        """Какие виды на экране: ``main`` — шесть главных, ``more`` — прочие шесть (FR-63)."""
        value = _map(await self._get("panels")).get(attempt.hex)
        return value if value == "more" else "main"

    async def set_panel(self, attempt: UUID, name: str) -> None:
        await self._put("panels", attempt, name)

    async def card(self, attempt: UUID) -> str:
        value = _map(await self._get("cards")).get(attempt.hex)
        return value if isinstance(value, str) else ""

    async def selected(self, attempt: UUID) -> int:
        value = _map(await self._get("selected")).get(attempt.hex)
        return value if isinstance(value, int) else 0

    async def select(self, attempt: UUID, cell: int) -> None:
        await self._put("selected", attempt, cell)

    async def draft(self, attempt: UUID) -> list[Mark]:
        """Черновик отметок записи: ``{"marks": {hex: [[клетка, вид, буква|null], …]}}``."""
        rows = _map(await self._get("marks")).get(attempt.hex)
        return [
            Mark(int(row[0]), MarkKind(row[1]), row[2])
            for row in (rows if isinstance(rows, list) else [])
            if isinstance(row, list) and len(row) == 3 and row[1] in MarkKind
        ]

    async def set_draft(self, attempt: UUID, marks: list[Mark]) -> None:
        rows = [[m.cell, str(m.kind), m.heard_letter] for m in marks]
        await self._put("marks", attempt, rows or None)


_STATUS: Final = {
    "bad": AnnotationStatus.AUDIO_UNUSABLE,
    "off": AnnotationStatus.OFF_TASK,
}


# ---------- один экран ----------
@dataclass(frozen=True, slots=True)
class Screen:
    """Что показано на карточке записи: черновик, выбранный слог и отметки до ответа."""

    task: AnnotationTask
    marks: list[Mark]
    selected: int
    has_reference: bool
    self_corrected: bool
    panel: str = "main"


async def _screen(desk: Desk, task: AnnotationTask, library: ReferenceAudioLibrary) -> Screen:
    attempt = task.attempt_id
    return Screen(
        task, await desk.draft(attempt), await desk.selected(attempt),
        library.has(task.item_id), await desk.self_corrected(attempt),
        await desk.panel(attempt),
    )  # fmt: skip


def _mark(a: str, step: str, cell: int = 0, kind: str = "", letter: str = "") -> str:
    return AnnotateMark(a=a, s=step, c=cell, k=kind, h=letter).pack()


def _kinds_text(marks: list[Mark], cell: int) -> str:
    return ", ".join(
        t.MARK_LETTER.format(kind=t.KIND_BUTTONS[str(m.kind)].lower(), letter=m.heard_letter)
        if m.heard_letter
        else t.KIND_BUTTONS[str(m.kind)].lower()
        for m in marks
        if m.cell == cell
    )


def _marked(task: AnnotationTask, marks: list[Mark]) -> str:
    """«„на“ — огласовка, буква (ء); „дُ“ — пропуск» — по слогам в порядке чтения."""
    return "; ".join(
        t.MARK_ITEM.format(piece=escape(task.cells[cell].piece), kinds=_kinds_text(marks, cell))
        for cell in sorted({m.cell for m in marks})
    )


def _screen_text(card: str, s: Screen) -> str:
    text = card
    if s.task.cells:
        text += t.SELECTED.format(piece=escape(s.task.cells[s.selected].piece))
    if s.marks:
        text += t.MARKED.format(marks=_marked(s.task, s.marks))
    return text


def _cell_rows(s: Screen) -> list[list[InlineKeyboardButton]]:
    """Ряд на слово (длинное — несколько рядов по 8), первый слог справа."""
    a = s.task.attempt_id.hex
    words: dict[int, list[int]] = {}
    for cell in s.task.cells:
        words.setdefault(cell.word, []).append(cell.index)
    marked = {m.cell for m in s.marks}
    rows: list[list[InlineKeyboardButton]] = []
    for members in words.values():
        pieces = [s.task.cells[n].piece for n in members]
        buttons = []
        for i, n in enumerate(members):
            piece = in_word(pieces, i)
            text = t.CELL_SELECTED.format(piece=piece) if n == s.selected else piece
            text = (
                (t.CELL_BOT if n in s.task.bot_cells else "")
                + text
                + (t.CELL_MARKED if n in marked else "")
            )
            buttons.append(InlineKeyboardButton(text=text, callback_data=_mark(a, "c", n)))
        rows += [buttons[k : k + MAX_ROW][::-1] for k in range(0, len(buttons), MAX_ROW)]
    return rows


def _kind_rows(s: Screen) -> list[list[InlineKeyboardButton]]:
    """Шесть главных видов по 2 в ряд и «Ещё»; в панели «Ещё» — прочие шесть и «Назад»."""
    a, cell = s.task.attempt_id.hex, s.selected
    chosen = {m.kind for m in s.marks if m.cell == cell}
    more = s.panel == "more"
    kinds = [
        InlineKeyboardButton(
            text=t.KIND_BUTTONS[str(kind)] + (t.KIND_ON if kind in chosen else ""),
            callback_data=_mark(a, "k", cell, kind.code),
        )
        for kind in (MORE_KINDS if more else MAIN_KINDS)
    ]
    rows = [kinds[k : k + KINDS_ROW] for k in range(0, len(kinds), KINDS_ROW)]
    switch = InlineKeyboardButton(
        text=t.BTN_BACK if more else t.BTN_MORE,
        callback_data=AnnotateAct(a=a, act="back" if more else "more").pack(),
    )
    return [*rows, [switch]]


def _action_rows(s: Screen) -> list[list[InlineKeyboardButton]]:
    a = s.task.attempt_id.hex

    def act(text: str, name: str) -> InlineKeyboardButton:
        return InlineKeyboardButton(text=text, callback_data=AnnotateAct(a=a, act=name).pack())

    bot_found = bool(s.task.bot_cells or s.task.bot_errors)
    actions = [
        *([] if s.marks else [act(t.BTN_BOT_RIGHT, "botright")]),
        *([act(t.BTN_FIX_BOT, "fixbot")] if bot_found and not s.marks else []),
        act(t.BTN_CLEAN, "clean"),
        InlineKeyboardButton(text=t.BTN_DONE, callback_data=_mark(a, "d")),
        *([act(t.BTN_REF, "ref")] if s.has_reference else []),
        act(t.BTN_SELF_ON if s.self_corrected else t.BTN_SELF, "self"),
        act(t.BTN_COMMENT, "comment"),
        act(t.BTN_BAD, "bad"),
        act(t.BTN_OFF, "off"),
        act(t.BTN_MANUAL, "fix"),
        act(t.BTN_SKIP, "skip"),
    ]
    return [actions[k : k + ACTIONS_ROW] for k in range(0, len(actions), ACTIONS_ROW)]


def _keyboard(s: Screen) -> InlineKeyboardMarkup:
    kinds = _kind_rows(s) if s.task.cells else []
    return InlineKeyboardMarkup(inline_keyboard=[*_cell_rows(s), *kinds, *_action_rows(s)])


def _letters_keyboard(s: Screen, curriculum: Curriculum) -> InlineKeyboardMarkup:
    """Шаг «какая буква» после «Буква»: что услышал бот, частые пары, «другая…», «не знаю»."""
    task, cell = s.task, s.selected
    a = task.attempt_id.hex
    written = written_letters(task.cells[cell].piece)
    heard = bot_letters(task.item_text, task.reference_phonemes, task.bot_heard, task.cells, cell)
    bot = [x for x in heard if x not in written]
    pairs = [x for x in pair_letters(written, curriculum.lexicon.pair_tips) if x not in bot]
    letters = [
        InlineKeyboardButton(
            text=t.LETTER_BOT.format(letter=x) if x in bot else x,
            callback_data=_mark(a, "h", cell, letter=x),
        )
        for x in bot + pairs
    ]
    rows = [letters[k : k + LETTER_ROW] for k in range(0, len(letters), LETTER_ROW)]
    rows.append([
        InlineKeyboardButton(text=t.BTN_OTHER_LETTER, callback_data=_mark(a, "o", cell)),
        InlineKeyboardButton(text=t.BTN_DONT_KNOW, callback_data=_mark(a, "n", cell)),
    ])  # fmt: skip
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _alphabet_keyboard(s: Screen, kind: MarkKind | None = None) -> InlineKeyboardMarkup:
    """«другая…»: все 28 согласных и «не знаю»."""
    a, cell = s.task.attempt_id.hex, s.selected
    code = kind.code if kind else ""
    letters = [
        InlineKeyboardButton(text=x, callback_data=_mark(a, "h", cell, code, x)) for x in ALPHABET
    ]
    rows = [letters[k : k + LETTER_ROW] for k in range(0, len(letters), LETTER_ROW)]
    rows.append(
        [InlineKeyboardButton(text=t.BTN_DONT_KNOW, callback_data=_mark(a, "n", cell, code))]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _pick(s: Screen, kind: MarkKind, text: str, value: str) -> InlineKeyboardButton:
    a = s.task.attempt_id.hex
    return InlineKeyboardButton(
        text=text, callback_data=_mark(a, "h", s.selected, kind.code, value)
    )


def _dont_know(s: Screen, kind: MarkKind, text: str = t.BTN_DONT_KNOW) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=text, callback_data=_mark(s.task.attempt_id.hex, "n", s.selected, kind.code)
    )


def _vowel_keyboard(s: Screen, kind: MarkKind) -> InlineKeyboardMarkup:
    """Какая гласная прозвучала: а / и / у (и «никакой» — у «Огласовка»)."""
    buttons = [_pick(s, kind, name, vowel) for vowel, name in t.VOWEL_NAMES.items()]
    if kind is MarkKind.VOWEL:
        buttons.append(_pick(s, kind, t.BTN_NO_VOWEL, NO_VOWEL))
    return InlineKeyboardMarkup(inline_keyboard=[buttons, [_dont_know(s, kind)]])


def _extra_keyboard(s: Screen) -> InlineKeyboardMarkup:
    """Какой звук добавил: ا و ي ن, любой другой, «не знаю»."""
    kind = MarkKind.EXTRA
    buttons = [_pick(s, kind, x, x) for x in "اوين"]
    other = InlineKeyboardButton(
        text=t.BTN_OTHER_LETTER,
        callback_data=_mark(s.task.attempt_id.hex, "o", s.selected, kind.code),
    )
    return InlineKeyboardMarkup(inline_keyboard=[buttons, [other, _dont_know(s, kind)]])


def _missing_keyboard(s: Screen) -> InlineKeyboardMarkup:
    """Что пропущено: звуки слога по одному или весь слог."""
    kind = MarkKind.MISSING
    task = s.task
    sounds = cell_sounds(task.item_text, task.reference_phonemes, task.cells, s.selected)
    buttons = [_pick(s, kind, t.VOWEL_NAMES.get(x, x), x) for x in sounds]
    return InlineKeyboardMarkup(inline_keyboard=[buttons, [_dont_know(s, kind, t.BTN_WHOLE_CELL)]])


def _question(
    s: Screen, kind: MarkKind, curriculum: Curriculum
) -> tuple[str, InlineKeyboardMarkup] | None:
    """Вопрос «что прозвучало» после вида; None — у вида вопроса нет."""
    piece = escape(s.task.cells[s.selected].piece)
    match kind:
        case MarkKind.LETTER:
            return t.LETTER_HEADER.format(piece=piece), _letters_keyboard(s, curriculum)
        case MarkKind.VOWEL:
            return t.VOWEL_HEADER.format(piece=piece), _vowel_keyboard(s, kind)
        case MarkKind.SUKUN:
            return t.SUKUN_HEADER.format(piece=piece), _vowel_keyboard(s, kind)
        case MarkKind.EXTRA:
            return t.EXTRA_HEADER.format(piece=piece), _extra_keyboard(s)
        case MarkKind.MISSING:
            return t.MISSING_HEADER.format(piece=piece), _missing_keyboard(s)
        case _:
            return None


async def _show(message: Message, text: str, markup: InlineKeyboardMarkup) -> None:
    """Текст и клавиатура карточки — на месте («не изменилось» Telegram — не ошибка)."""
    with suppress(TelegramBadRequest):
        await message.edit_text(text, reply_markup=markup)


async def _refresh(
    message: Message, desk: Desk, task: AnnotationTask, library: ReferenceAudioLibrary
) -> None:
    s = await _screen(desk, task, library)
    await _show(message, _screen_text(await desk.card(task.attempt_id), s), _keyboard(s))


# ---------- карточка записи ----------
def _cancel(attempt: UUID) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=t.BTN_CANCEL, callback_data=AnnotateAct(a=attempt.hex, act="cancel"))
    return kb.as_markup()


def _redo(attempt: UUID) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=t.BTN_REDO, callback_data=AnnotateAct(a=attempt.hex, act="redo"))
    return kb.as_markup()


async def _saved(message: Message, attempt: UUID, *, saved: bool, text: str = t.SAVED) -> None:
    """«Сохранено» с кнопкой «Переделать» — или «записи больше нет»."""
    if saved:
        await message.answer(text, reply_markup=_redo(attempt))
    else:
        await message.answer(t.GONE)


def _card(shown: ShownTask) -> str:
    task = shown.task
    where = (
        t.WHERE.format(page=task.page, line=task.line, item=escape(task.item_id))
        if task.page is not None and task.line is not None
        else t.WHERE_ITEM.format(item=escape(task.item_id))
    )
    listed = "; ".join(
        f"{n}) {escape(e or '—')} → {escape(h or '—')}"
        for n, (e, h) in enumerate(task.bot_errors, start=1)
    )
    reason = t.LEARNER_REASONS.get(task.learner_says or "", "")
    found = ", ".join(f"«{escape(c.piece)}»" for c in task.cells if c.index in task.bot_cells)
    hint = t.BOT_FOUND.format(pieces=found) if found else ("" if listed else t.NO_ERRORS)
    return t.TASK.format(
        annotator=escape(shown.annotator), remaining=shown.remaining, where=where,
        item_text=escape(task.item_text or "—"), hint=hint,
        errors=t.ERRORS.format(errors=listed) if listed else "",
        bot_heard=escape(task.bot_heard), reference=escape(task.reference_phonemes),
        learner=t.LEARNER_SAYS.format(reason=reason) if reason else "",
    )  # fmt: skip


async def _show_next(
    bot: Bot,
    chat_id: int,
    learner: Learner,
    desk: Desk,
    uc: NextAnnotation,
    library: ReferenceAudioLibrary,
) -> None:
    shown = await uc.execute(learner, await desk.skipped())
    if shown is None:
        await bot.send_message(chat_id, t.DONE)
        return
    await _send_task(bot, chat_id, desk, shown, library)


async def _continue(
    bot: Bot,
    chat_id: int,
    learner: Learner,
    desk: Desk,
    uc: NextAnnotation,
    library: ReferenceAudioLibrary,
    answered: UUID,
) -> None:
    """После ответа: следующая запись — или назад к текущей, если отвечали на «Переделать»."""
    if await desk.done_redo(answered):
        await bot.send_message(chat_id, t.BACK_TO_CURRENT)
    else:
        await _show_next(bot, chat_id, learner, desk, uc, library)


async def _send_task(
    bot: Bot, chat_id: int, desk: Desk, shown: ShownTask, library: ReferenceAudioLibrary
) -> None:
    """Запись и карточка — один экран. Сразу выбран первый слог, где ошибку нашёл бот."""
    task = shown.task
    card = _card(shown)
    await desk.shown(task.attempt_id)
    await desk.open(task.attempt_id, card, min(task.bot_cells, default=0))
    await bot.send_voice(
        chat_id, BufferedInputFile(shown.audio, filename="attempt.ogg"), protect_content=True
    )
    s = await _screen(desk, task, library)
    await bot.send_message(
        chat_id, _screen_text(card, s), protect_content=True, reply_markup=_keyboard(s)
    )


async def _submit(
    learner: Learner,
    desk: Desk,
    submit: SubmitAnnotation,
    attempt: UUID,
    status: AnnotationStatus,
    actual: str | None = None,
) -> bool:
    """Сохранить ответ разметчика. В лог не пишется: событие — в БД (ADR-0027 п. 4)."""
    saved = await submit.execute(
        learner, attempt, status, actual=actual, reading=actual is not None,
        seconds_spent=await desk.seconds(attempt),
        self_corrected=await desk.self_corrected(attempt), comment=await desk.comment(attempt),
    )  # fmt: skip
    await desk.close(attempt)
    return saved


async def _waiting_for_fix(message: Message, state: FSMContext) -> bool:
    return await Desk(state).fixing() is not None


async def _waiting_for_comment(message: Message, state: FSMContext) -> bool:
    return await Desk(state).commenting() is not None


async def _drop_buttons(cb: CallbackQuery) -> None:
    """Кнопки ответа убираются: одну запись нельзя случайно разметить дважды."""
    if isinstance(cb.message, Message):
        with suppress(TelegramBadRequest):
            await cb.message.edit_reply_markup(reply_markup=None)


@router.message(Command("annotate"))
async def annotate(
    m: Message,
    bot: Bot,
    command: CommandObject,
    state: FSMContext,
    learner: FromDishka[Learner],
    join: FromDishka[JoinAnnotation],
    redeem: FromDishka[RedeemInvite],
    uc: FromDishka[NextAnnotation],
    library: FromDishka[ReferenceAudioLibrary],
) -> None:
    if command.args and looks_like_invite(command.args):
        result, annotator = await redeem.execute(learner, command.args)
        if result is RedeemResult.GRANTED:
            await m.answer(t.INVITE_OK.format(annotator=escape(annotator or "")))
        else:
            await m.answer(t.INVITE_LOCKED if result is RedeemResult.LOCKED else t.INVITE_INVALID)
            return
    joined = await join.execute(learner)
    if joined is None:
        raise SkipHandler  # доступ отозван: как обычное сообщение ученика
    annotator, first_time = joined
    if first_time:
        await m.answer(t.WELCOME.format(annotator=escape(annotator)))
    desk = Desk(state)
    await desk.start_over()
    await _show_next(bot, m.chat.id, learner, desk, uc, library)


@router.message(F.text, _waiting_for_fix)
async def fixed_phonemes(
    m: Message,
    bot: Bot,
    state: FSMContext,
    learner: FromDishka[Learner],
    submit: FromDishka[SubmitAnnotation],
    uc: FromDishka[NextAnnotation],
    library: FromDishka[ReferenceAudioLibrary],
) -> None:
    """«Фонемы вручную»: что прозвучало; «бот прав» — тем же правилом, что у клеток."""
    desk = Desk(state)
    attempt = await desk.fixing()
    assert attempt is not None  # гарантирует фильтр _waiting_for_fix  # noqa: S101
    try:
        saved = await _submit(learner, desk, submit, attempt, AnnotationStatus.FIX, m.text or "")
    except LabelError as error:
        await desk.shown(attempt, keep=True)
        await m.answer(t.FIX_WRONG.format(error=escape(str(error))), reply_markup=_cancel(attempt))
        return
    except NotAnnotator:
        await desk.set_fixing(None)
        raise SkipHandler from None
    await desk.set_fixing(None)
    await _saved(m, attempt, saved=saved)
    await _continue(bot, m.chat.id, learner, desk, uc, library, attempt)


@router.message(F.text, _waiting_for_comment)
async def comment_text(
    m: Message, state: FSMContext, access: FromDishka[AnnotatorAccess], learner: FromDishka[Learner]
) -> None:
    """«Комментарий»: текст уйдёт в ``annotations.comment`` со следующим ответом на запись."""
    desk = Desk(state)
    attempt = await desk.commenting()
    assert attempt is not None  # гарантирует фильтр _waiting_for_comment  # noqa: S101
    await desk.set_commenting(None)
    if await access.code_for(learner.telegram_user_id) is None:
        raise SkipHandler
    await desk.set_comment(attempt, (m.text or "").strip())
    await m.answer(t.COMMENT_OK)


async def _toggle_self_correction(
    message: Message,
    desk: Desk,
    attempt: UUID,
    marks: SubmitMarks,
    library: ReferenceAudioLibrary,
) -> None:
    """«Сам исправился» — переключатель до ответа; галочка на кнопке показывает состояние."""
    await desk.toggle_self_corrected(attempt)
    task = await marks.task(attempt)
    if task is not None:
        await _refresh(message, desk, task, library)


async def _send_reference(
    bot: Bot, chat_id: int, attempt: UUID, submit: SubmitAnnotation, library: ReferenceAudioLibrary
) -> bool:
    """«Эталон». False — эталона для этой карточки нет."""
    task = await submit.tasks.get(attempt)
    audio = await library.get(task.item_id) if task else None
    if audio is None:
        return False
    name = "reference.ogg" if audio[:4] == b"OggS" else "reference.mp3"
    await bot.send_audio(chat_id, BufferedInputFile(audio, filename=name))
    return True


async def _redo_task(
    message: Message,
    bot: Bot,
    learner: Learner,
    desk: Desk,
    uc: NextAnnotation,
    library: ReferenceAudioLibrary,
    attempt: UUID,
) -> None:
    """«Переделать»: та же запись снова; новый ответ заменит прежний в данных."""
    again = await uc.again(learner, attempt)
    if again is None:
        await message.answer(t.GONE)
    else:
        await _send_task(bot, message.chat.id, desk, again, library)


async def _answer(
    cb: CallbackQuery,
    learner: Learner,
    desk: Desk,
    submit: SubmitAnnotation,
    attempt: UUID,
    status: AnnotationStatus,
) -> bool:
    """Ответ кнопкой («Плохая запись», «Читал не то»). False — не сохранён, разметчику уже
    ответили всплывающим окном."""
    assert isinstance(cb.message, Message)  # проверено в act  # noqa: S101
    try:
        saved = await _submit(learner, desk, submit, attempt, status)
    except NotAnnotator:  # доступ отозвали, пока запись была на экране
        await cb.answer()
        return False
    except LabelError as error:  # «сам исправился» у плохой записи или чужого текста
        await cb.answer(str(error), show_alert=True)
        return False
    await _drop_buttons(cb)
    await _saved(cb.message, attempt, saved=saved)
    return True


async def _save_marks(
    cb: CallbackQuery, learner: Learner, desk: Desk, marks_uc: SubmitMarks, attempt: UUID
) -> bool:
    """«Чисто» (без отметок) или «Готово» (черновик). False — не сохранено, уже ответили."""
    assert isinstance(cb.message, Message)  # проверено в обработчике  # noqa: S101
    marks = await desk.draft(attempt)
    task = await marks_uc.task(attempt)
    try:
        saved = await marks_uc.execute(
            learner, attempt, marks, seconds_spent=await desk.seconds(attempt),
            self_corrected=await desk.self_corrected(attempt),
            comment=await desk.comment(attempt),
        )  # fmt: skip
    except NotAnnotator:
        await cb.answer()
        return False
    except LabelError as error:
        await desk.shown(attempt, keep=True)
        await cb.answer(str(error), show_alert=True)
        return False
    await desk.close(attempt)
    await _drop_buttons(cb)
    text = t.SAVED_MARKS.format(marks=_marked(task, marks)) if task and marks else t.SAVED
    await _saved(cb.message, attempt, saved=saved, text=text)
    return True


async def _bot_right(
    cb: CallbackQuery, learner: Learner, desk: Desk, marks_uc: SubmitMarks, attempt: UUID
) -> bool:
    """«Бот прав» (FR-63): ответ бота как «что прозвучало». False — не сохранено."""
    assert isinstance(cb.message, Message)  # проверено в act  # noqa: S101
    if await desk.draft(attempt):  # свои отметки не теряем: «Бот прав» их не заменит
        await cb.answer(t.BOT_RIGHT_DRAFT, show_alert=True)
        return False
    try:
        saved = await marks_uc.confirm_bot(
            learner, attempt, seconds_spent=await desk.seconds(attempt),
            self_corrected=await desk.self_corrected(attempt),
            comment=await desk.comment(attempt),
        )  # fmt: skip
    except NotAnnotator:
        await cb.answer()
        return False
    except LabelError as error:
        await desk.shown(attempt, keep=True)
        await cb.answer(str(error), show_alert=True)
        return False
    await desk.close(attempt)
    await _drop_buttons(cb)
    await _saved(cb.message, attempt, saved=saved)
    return True


async def _show_panel(
    message: Message,
    desk: Desk,
    marks_uc: SubmitMarks,
    library: ReferenceAudioLibrary,
    attempt: UUID,
    panel: str,
) -> None:
    """«Ещё» / «Назад»: другие виды на том же экране."""
    task = await marks_uc.task(attempt)
    if task is not None:
        await desk.set_panel(attempt, panel)
        await _refresh(message, desk, task, library)


async def _load_bot_marks(
    message: Message,
    desk: Desk,
    marks_uc: SubmitMarks,
    library: ReferenceAudioLibrary,
    attempt: UUID,
) -> None:
    """«Исправить»: отметки бота — в черновик, дальше учитель правит спорное."""
    task = await marks_uc.task(attempt)
    if task is None:
        return
    found = marks_from_bot(task.item_text, task.reference_phonemes, task.bot_heard, task.cells)
    await desk.set_draft(attempt, list(found))
    await _refresh(message, desk, task, library)


async def _clean(
    cb: CallbackQuery, learner: Learner, desk: Desk, marks_uc: SubmitMarks, attempt: UUID
) -> bool:
    """«Чисто» — метка клетками без отметок (черновик, если был, отбрасывается)."""
    await desk.set_draft(attempt, [])
    return await _save_marks(cb, learner, desk, marks_uc, attempt)


async def _input_act(
    cb: CallbackQuery,
    name: str,
    desk: Desk,
    submit: SubmitAnnotation,
    marks_uc: SubmitMarks,
    library: ReferenceAudioLibrary,
    attempt: UUID,
) -> None:
    """«Фонемы вручную», «Комментарий», «Сам исправился», «Отмена» — ввод и переключатели."""
    assert isinstance(cb.message, Message)  # проверено в act  # noqa: S101
    if name == "fix":
        await desk.set_fixing(attempt)
        task = await submit.tasks.get(attempt)
        await cb.message.answer(
            t.FIX_ASK.format(bot_heard=escape(task.bot_heard if task else "")),
            reply_markup=_cancel(attempt),
        )
    elif name == "comment":
        await desk.set_commenting(attempt)
        await cb.message.answer(t.COMMENT_ASK)
    elif name == "self":
        await _toggle_self_correction(cb.message, desk, attempt, marks_uc, library)
    else:
        await desk.set_fixing(None)
        await _drop_buttons(cb)


_BOARD: Final = frozenset({"botright", "fixbot", "more", "back"})  # FR-63


async def _board(
    cb: CallbackQuery,
    name: str,
    learner: Learner,
    desk: Desk,
    marks_uc: SubmitMarks,
    library: ReferenceAudioLibrary,
    attempt: UUID,
) -> bool:
    """«Бот прав», «Исправить», «Ещё», «Назад». True — запись сохранена, показать следующую;
    во всех остальных случаях на нажатие уже ответили."""
    assert isinstance(cb.message, Message)  # проверено в act  # noqa: S101
    if not await desk.marking(attempt):
        await cb.answer()  # запись уже сохранена или пропущена: кнопки не действуют
        return False
    if name == "botright":
        return await _bot_right(cb, learner, desk, marks_uc, attempt)
    if name == "fixbot":
        await _load_bot_marks(cb.message, desk, marks_uc, library, attempt)
    else:
        await _show_panel(
            cb.message, desk, marks_uc, library, attempt, "more" if name == "more" else "main"
        )
    await cb.answer()
    return False


@router.callback_query(AnnotateAct.filter())
async def act(
    cb: CallbackQuery,
    bot: Bot,
    callback_data: AnnotateAct,
    state: FSMContext,
    learner: FromDishka[Learner],
    access: FromDishka[AnnotatorAccess],
    submit: FromDishka[SubmitAnnotation],
    marks: FromDishka[SubmitMarks],
    uc: FromDishka[NextAnnotation],
    library: FromDishka[ReferenceAudioLibrary],
) -> None:
    tg = learner.telegram_user_id
    try:
        attempt = UUID(hex=callback_data.a)
    except ValueError:
        await cb.answer()
        return
    if await access.code_for(tg) is None or not isinstance(cb.message, Message):
        await cb.answer()  # посторонний или старая кнопка: молча ничего
        return
    chat_id = cb.message.chat.id
    desk = Desk(state)
    if callback_data.act in _BOARD:
        if await _board(cb, callback_data.act, learner, desk, marks, library, attempt):
            await _continue(bot, chat_id, learner, desk, uc, library, attempt)
            await cb.answer()
        return
    match callback_data.act:
        case "fix" | "comment" | "self" | "cancel":
            await _input_act(cb, callback_data.act, desk, submit, marks, library, attempt)
        case "ref":
            if not await _send_reference(bot, chat_id, attempt, submit, library):
                await cb.answer(t.NO_REFERENCE, show_alert=True)
                return
        case "skip":
            await desk.close(attempt)
            await desk.skip(attempt)
            await desk.seconds(attempt)  # снять отметку времени показа
            await _drop_buttons(cb)
            await _continue(bot, chat_id, learner, desk, uc, library, attempt)
        case "redo":
            await desk.redoing(attempt)  # ввод фонем текущей записи (fixing) не сбрасываем
            await _drop_buttons(cb)
            await _redo_task(cb.message, bot, learner, desk, uc, library, attempt)
        case "clean" if not await desk.marking(attempt):
            await cb.answer()  # запись уже сохранена или пропущена: кнопка не действует
            return
        case name if name in _STATUS or name == "clean":
            answered = (
                _clean(cb, learner, desk, marks, attempt)
                if name == "clean"
                else _answer(cb, learner, desk, submit, attempt, _STATUS[name])
            )
            if not await answered:
                return
            await _continue(bot, chat_id, learner, desk, uc, library, attempt)
    await cb.answer()


# ---------- слог → вид (→ буква) ----------
def _toggle(marks: list[Mark], cell: int, kind: MarkKind) -> tuple[list[Mark], bool]:
    """Вид в слоге вкл/выкл; второе — включён ли теперь."""
    kept = [m for m in marks if not (m.cell == cell and m.kind is kind)]
    if len(kept) < len(marks):
        return kept, False
    return [*marks, Mark(cell, kind)], True


def _with_answer(marks: list[Mark], cell: int, kind: MarkKind, heard: str | None) -> list[Mark]:
    """Вид в слоге — с ответом «что прозвучало» (или без него: «не знаю»)."""
    others = [m for m in marks if not (m.cell == cell and m.kind is kind)]
    return [*others, Mark(cell, kind, heard)]


async def _marking_task(
    data: AnnotateMark,
    desk: Desk,
    access: AnnotatorAccess,
    marks_uc: SubmitMarks,
    learner: Learner,
) -> AnnotationTask | None:
    """Задача, если кнопка годится: свой разметчик, запись на экране и не сохранена, слог в
    раскладке. Иначе None — молча ничего."""
    try:
        attempt = UUID(hex=data.a)
    except ValueError:
        return None
    stranger = await access.code_for(learner.telegram_user_id) is None
    if stranger or not await desk.marking(attempt):
        return None  # чужой, уже сохранено или пропущено
    task = await marks_uc.task(attempt)
    if task is None or (data.s != "d" and not 0 <= data.c < len(task.cells)):
        return None
    return task


async def _step(
    message: Message,
    data: AnnotateMark,
    desk: Desk,
    task: AnnotationTask,
    library: ReferenceAudioLibrary,
    curriculum: Curriculum,
) -> str | None:
    """Шаг разметки на месте. Возвращает текст всплывающего окна или None."""
    attempt, cell = task.attempt_id, data.c
    marks = await desk.draft(attempt)
    asked: tuple[str, InlineKeyboardMarkup] | None = None
    answer_kind = MarkKind.by_code(data.k) if data.k else MarkKind.LETTER
    match data.s:
        case "c":
            await desk.select(attempt, cell)
        case "k" if (kind := MarkKind.by_code(data.k)) is not None:
            await desk.select(attempt, cell)
            await desk.set_panel(attempt, "main")
            marks, on = _toggle(marks, cell, kind)
            await desk.set_draft(attempt, marks)
            if on:
                asked = _question(await _screen(desk, task, library), kind, curriculum)
        case "l":
            asked = _question(await _screen(desk, task, library), MarkKind.LETTER, curriculum)
        case "o" if answer_kind is not None:
            header = t.LETTER_HEADER.format(piece=escape(task.cells[cell].piece))
            screen = await _screen(desk, task, library)
            asked = (header, _alphabet_keyboard(screen, answer_kind if data.k else None))
        case "h" | "n" if answer_kind is not None:
            marks = _with_answer(marks, cell, answer_kind, data.h if data.s == "h" else None)
            try:
                check_marks(task.cells, marks)
            except LabelError as error:
                return str(error)
            await desk.set_draft(attempt, marks)
    if asked is not None:
        header, keyboard = asked
        await _show(message, await desk.card(attempt) + header, keyboard)
    else:
        await _refresh(message, desk, task, library)
    return None


@router.callback_query(AnnotateMark.filter())
async def mark(
    cb: CallbackQuery,
    bot: Bot,
    callback_data: AnnotateMark,
    state: FSMContext,
    learner: FromDishka[Learner],
    access: FromDishka[AnnotatorAccess],
    marks_uc: FromDishka[SubmitMarks],
    uc: FromDishka[NextAnnotation],
    library: FromDishka[ReferenceAudioLibrary],
    curriculum: FromDishka[Curriculum],
) -> None:
    """Слог → вид (→ буква) → «Готово». Чужая, старая или подделанная кнопка — молча ничего."""
    desk = Desk(state)
    task = await _marking_task(callback_data, desk, access, marks_uc, learner)
    if task is None or not isinstance(cb.message, Message):
        await cb.answer()
        return
    if callback_data.s != "d":
        alert = await _step(cb.message, callback_data, desk, task, library, curriculum)
        await cb.answer(alert, show_alert=alert is not None)
        return
    if not await desk.draft(task.attempt_id):
        await cb.answer(t.DONE_EMPTY, show_alert=True)  # без отметок — подсказка, не метка
        return
    if not await _save_marks(cb, learner, desk, marks_uc, task.attempt_id):
        return
    await _continue(bot, cb.message.chat.id, learner, desk, uc, library, task.attempt_id)
    await cb.answer()

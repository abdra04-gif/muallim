"""Разметка в Telegram (FR-17, ADR-0041): /annotate, кнопки разметчика, исправление фонем.

Посторонний не видит разметку вовсе: без доступа /annotate уходит обычному обработчику ученика
(SkipHandler), а кнопки молча ничего не делают — права проверяет сценарий при каждом действии.
Записи учеников отправляются с protect_content: их нельзя переслать или сохранить. Только личный
чат. Роутер подключается раньше роутера ученика (bootstrap/main.py: ``routers()``).
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
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dishka import FromDishka

from muallim.application.ports.storage import ReferenceAudioLibrary
from muallim.application.use_cases.annotation import (
    AnnotatorAccess,
    NextAnnotation,
    NotAnnotator,
    RedeemInvite,
    RedeemResult,
    ShownTask,
    SubmitAnnotation,
)
from muallim.domain.annotation import AnnotationStatus, AnnotationTask, LabelError
from muallim.domain.learner import Learner
from muallim.presentation.telegram import annotator_texts as t
from muallim.presentation.telegram.callbacks import AnnotateAct

router: Final = Router(name="annotator")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")


@dataclass(frozen=True, slots=True)
class Desk:
    """Что разметчик делает сейчас — в FSM aiogram, свой у каждого чата и диспетчера.

    Хранится только JSON-совместимое (hex попыток, секунды). Время показа — по ``time.monotonic``,
    как до ADR-0049: при постоянном хранилище FSM (TD-FN-70) перейти на часы с защитой от
    отрицательных значений. Не данные исследования: ответ — в БД.
    """

    state: FSMContext

    async def _get(self) -> dict[str, object]:
        return await self.state.get_data()

    async def fixing(self) -> UUID | None:
        """Попытка, для которой ждём исправленные фонемы текстом."""
        value = (await self._get()).get("fixing")
        return UUID(hex=value) if isinstance(value, str) else None

    async def set_fixing(self, attempt: UUID | None) -> None:
        await self.state.update_data({"fixing": attempt.hex if attempt else None})

    async def skipped(self) -> frozenset[UUID]:
        """Пропущенные в этот заход — не показывать снова."""
        value = (await self._get()).get("skipped") or []
        return frozenset(UUID(hex=h) for h in value) if isinstance(value, list) else frozenset()

    async def skip(self, attempt: UUID) -> None:
        await self.state.update_data(
            {"skipped": sorted({a.hex for a in await self.skipped()} | {attempt.hex})}
        )

    async def self_corrected(self, attempt: UUID) -> bool:
        value = (await self._get()).get("self_corrected") or []
        return isinstance(value, list) and attempt.hex in value

    async def toggle_self_corrected(self, attempt: UUID) -> bool:
        """«🔁 Сам исправился» — переключатель до ответа; возвращает новое значение."""
        value = (await self._get()).get("self_corrected") or []
        marked = set(value) if isinstance(value, list) else set()
        marked.symmetric_difference_update({attempt.hex})
        await self.state.update_data({"self_corrected": sorted(marked)})
        return attempt.hex in marked

    async def forget_self_corrected(self, attempt: UUID) -> None:
        value = (await self._get()).get("self_corrected") or []
        marked = set(value) if isinstance(value, list) else set()
        await self.state.update_data({"self_corrected": sorted(marked - {attempt.hex})})

    async def shown(self, attempt: UUID, *, keep: bool = False) -> None:
        """Когда показана запись — для времени ответа; ``keep`` — не сбрасывать уже отмеченное."""
        value = (await self._get()).get("shown_at") or {}
        times = dict(value) if isinstance(value, dict) else {}
        if not (keep and attempt.hex in times):
            times[attempt.hex] = time.monotonic()
        await self.state.update_data({"shown_at": times})

    async def seconds(self, attempt: UUID) -> int | None:
        """Сколько секунд разметчик думал над записью; отметка снимается."""
        value = (await self._get()).get("shown_at") or {}
        times = dict(value) if isinstance(value, dict) else {}
        started = times.pop(attempt.hex, None)
        await self.state.update_data({"shown_at": times})
        return round(time.monotonic() - started) if isinstance(started, float | int) else None

    async def start_over(self) -> None:
        """Новый заход /annotate: не ждём исправления, пропущенные снова доступны."""
        await self.state.update_data({"fixing": None, "skipped": []})


_STATUS: Final = {
    "ok": AnnotationStatus.AGREE,
    "bad": AnnotationStatus.AUDIO_UNUSABLE,
    "off": AnnotationStatus.OFF_TASK,
}


def _keyboard(
    task: AnnotationTask, has_reference: bool, self_corrected: bool = False
) -> InlineKeyboardMarkup:
    a = task.attempt_id.hex
    kb = InlineKeyboardBuilder()
    kb.button(text=t.BTN_OK, callback_data=AnnotateAct(a=a, act="ok"))
    kb.button(text=t.BTN_FIX, callback_data=AnnotateAct(a=a, act="fix"))
    kb.button(
        text=t.BTN_SELF_ON if self_corrected else t.BTN_SELF,
        callback_data=AnnotateAct(a=a, act="self"),
    )
    kb.button(text=t.BTN_BAD, callback_data=AnnotateAct(a=a, act="bad"))
    kb.button(text=t.BTN_OFF, callback_data=AnnotateAct(a=a, act="off"))
    if has_reference:
        kb.button(text=t.BTN_REF, callback_data=AnnotateAct(a=a, act="ref"))
    kb.button(text=t.BTN_SKIP, callback_data=AnnotateAct(a=a, act="skip"))
    kb.button(text=t.BTN_STOP, callback_data=AnnotateAct(a=a, act="stop"))
    kb.adjust(1, 1, 1, 2, *((1,) if has_reference else ()), 2)
    return kb.as_markup()


def _cancel(attempt: UUID) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=t.BTN_CANCEL, callback_data=AnnotateAct(a=attempt.hex, act="cancel"))
    return kb.as_markup()


def _task_text(shown: ShownTask) -> str:
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
    return t.TASK.format(
        annotator=escape(shown.annotator), remaining=shown.remaining, where=where,
        item_text=escape(task.item_text or "—"),
        verdict=t.VERDICT_PASSED if task.bot_passed else t.VERDICT_FAILED,
        errors=t.ERRORS.format(errors=listed) if listed else t.NO_ERRORS,
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
    await desk.shown(shown.task.attempt_id)
    await bot.send_voice(
        chat_id, BufferedInputFile(shown.audio, filename="attempt.ogg"), protect_content=True
    )
    await bot.send_message(
        chat_id, _task_text(shown), protect_content=True,
        reply_markup=_keyboard(shown.task, library.has(shown.task.item_id)),
    )  # fmt: skip


async def _submit(
    learner: Learner,
    desk: Desk,
    submit: SubmitAnnotation,
    attempt: UUID,
    status: AnnotationStatus,
    actual: str | None = None,
) -> bool:
    """Сохранить ответ разметчика. В лог не пишется: событие — в БД (ADR-0027 п. 4)."""
    extra = {} if actual is None else {"actual": actual}
    saved = await submit.execute(
        learner, attempt, status, seconds_spent=await desk.seconds(attempt),
        self_corrected=await desk.self_corrected(attempt), **extra,
    )  # fmt: skip
    await desk.forget_self_corrected(attempt)
    return saved


async def _waiting_for_fix(message: Message, state: FSMContext) -> bool:
    return await Desk(state).fixing() is not None


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
    access: FromDishka[AnnotatorAccess],
    redeem: FromDishka[RedeemInvite],
    uc: FromDishka[NextAnnotation],
    library: FromDishka[ReferenceAudioLibrary],
) -> None:
    tg = learner.telegram_user_id
    if command.args:
        result, annotator = await redeem.execute(learner, command.args)
        if result is RedeemResult.GRANTED:
            await m.answer(t.INVITE_OK.format(annotator=escape(annotator or "")))
        else:
            await m.answer(t.INVITE_LOCKED if result is RedeemResult.LOCKED else t.INVITE_INVALID)
            return
    if await access.code_for(tg) is None:
        raise SkipHandler  # как обычное сообщение ученика: о разметке посторонний не узнает
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
    await m.answer(t.SAVED if saved else t.GONE)
    await _show_next(bot, m.chat.id, learner, desk, uc, library)


async def _toggle_self_correction(
    message: Message,
    desk: Desk,
    attempt: UUID,
    submit: SubmitAnnotation,
    library: ReferenceAudioLibrary,
) -> None:
    """«🔁 Сам исправился» — переключатель до ответа; галочка на кнопке показывает состояние."""
    marked = await desk.toggle_self_corrected(attempt)
    task = await submit.tasks.get(attempt)
    if task is not None:
        markup = _keyboard(task, library.has(task.item_id), marked)
        with suppress(TelegramBadRequest):
            await message.edit_reply_markup(reply_markup=markup)


@router.callback_query(AnnotateAct.filter())
async def act(
    cb: CallbackQuery,
    bot: Bot,
    callback_data: AnnotateAct,
    state: FSMContext,
    learner: FromDishka[Learner],
    access: FromDishka[AnnotatorAccess],
    submit: FromDishka[SubmitAnnotation],
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
    match callback_data.act:
        case "fix":
            await desk.set_fixing(attempt)
            task = await submit.tasks.get(attempt)
            await cb.message.answer(
                t.FIX_ASK.format(bot_heard=escape(task.bot_heard if task else "")),
                reply_markup=_cancel(attempt),
            )
        case "self":
            await _toggle_self_correction(cb.message, desk, attempt, submit, library)
        case "cancel":
            await desk.set_fixing(None)
            await _drop_buttons(cb)
        case "ref":
            task = await submit.tasks.get(attempt)
            audio = await library.get(task.item_id) if task else None
            if audio is None:
                await cb.answer(t.NO_REFERENCE, show_alert=True)
                return
            name = "reference.ogg" if audio[:4] == b"OggS" else "reference.mp3"
            await bot.send_audio(chat_id, BufferedInputFile(audio, filename=name))
        case "skip":
            await desk.forget_self_corrected(attempt)
            await desk.skip(attempt)
            await desk.seconds(attempt)  # снять отметку времени показа
            await _drop_buttons(cb)
            await _show_next(bot, chat_id, learner, desk, uc, library)
        case "stop":
            await desk.set_fixing(None)
            await _drop_buttons(cb)
            await cb.message.answer(t.STOPPED)
        case act_name if act_name in _STATUS:
            try:
                saved = await _submit(learner, desk, submit, attempt, _STATUS[act_name])
            except NotAnnotator:  # доступ отозвали, пока запись была на экране
                await cb.answer()
                return
            except LabelError as error:  # «сам исправился» у плохой записи или чужого текста
                await cb.answer(str(error), show_alert=True)
                return
            await _drop_buttons(cb)
            await cb.message.answer(t.SAVED if saved else t.GONE)
            await _show_next(bot, chat_id, learner, desk, uc, library)
    await cb.answer()

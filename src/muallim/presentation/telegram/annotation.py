"""Разметка в Telegram (FR-17, ADR-0041): /annotate, кнопки разметчика, исправление фонем.

Посторонний не видит разметку вовсе: без доступа /annotate уходит обычному обработчику ученика
(SkipHandler), а кнопки молча ничего не делают — права проверяет сценарий при каждом действии.
Записи учеников отправляются с protect_content: их нельзя переслать или сохранить. Только личный
чат. Роутер подключается раньше роутера ученика (bootstrap/main.py: ``routers()``).
"""

import time
from contextlib import suppress
from html import escape
from typing import Final
from uuid import UUID

from aiogram import Bot, F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
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

# Память процесса (сбрасывается при перезапуске — это не данные исследования):
_fixing: dict[int, UUID] = {}  # разметчик → попытка, для которой ждём исправленные фонемы
_shown_at: dict[tuple[int, UUID], float] = {}  # когда показана запись — время ответа
_skipped: dict[int, set[UUID]] = {}  # пропущенные в этот заход
_self_corrected: set[tuple[int, UUID]] = set()  # отмечено «сам исправился» (до ответа)

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
    bot: Bot, chat_id: int, learner: Learner, uc: NextAnnotation, library: ReferenceAudioLibrary
) -> None:
    tg = learner.telegram_user_id
    shown = await uc.execute(learner, frozenset(_skipped.get(tg, set())))
    if shown is None:
        await bot.send_message(chat_id, t.DONE)
        return
    _shown_at[(tg, shown.task.attempt_id)] = time.monotonic()
    await bot.send_voice(
        chat_id, BufferedInputFile(shown.audio, filename="attempt.ogg"), protect_content=True
    )
    await bot.send_message(
        chat_id, _task_text(shown), protect_content=True,
        reply_markup=_keyboard(shown.task, library.has(shown.task.item_id)),
    )  # fmt: skip


def _seconds(tg: int, attempt: UUID) -> int | None:
    started = _shown_at.pop((tg, attempt), None)
    return None if started is None else round(time.monotonic() - started)


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
    _fixing.pop(tg, None)
    _skipped.pop(tg, None)
    await _show_next(bot, m.chat.id, learner, uc, library)


@router.message(F.text, lambda m: m.from_user is not None and m.from_user.id in _fixing)
async def fixed_phonemes(
    m: Message,
    bot: Bot,
    learner: FromDishka[Learner],
    submit: FromDishka[SubmitAnnotation],
    uc: FromDishka[NextAnnotation],
    library: FromDishka[ReferenceAudioLibrary],
) -> None:
    tg = learner.telegram_user_id
    attempt = _fixing[tg]
    try:
        saved = await submit.execute(
            learner, attempt, AnnotationStatus.FIX, actual=m.text or "",
            seconds_spent=_seconds(tg, attempt),
            self_corrected=(tg, attempt) in _self_corrected,
        )  # fmt: skip
    except LabelError as error:
        _shown_at.setdefault((tg, attempt), time.monotonic())
        await m.answer(t.FIX_WRONG.format(error=escape(str(error))), reply_markup=_cancel(attempt))
        return
    except NotAnnotator:
        _fixing.pop(tg, None)
        raise SkipHandler from None
    _fixing.pop(tg, None)
    _self_corrected.discard((tg, attempt))
    await m.answer(t.SAVED if saved else t.GONE)
    await _show_next(bot, m.chat.id, learner, uc, library)


async def _toggle_self_correction(
    message: Message,
    tg: int,
    attempt: UUID,
    submit: SubmitAnnotation,
    library: ReferenceAudioLibrary,
) -> None:
    """«🔁 Сам исправился» — переключатель до ответа; галочка на кнопке показывает состояние."""
    key = (tg, attempt)
    _self_corrected.symmetric_difference_update({key})
    task = await submit.tasks.get(attempt)
    if task is not None:
        markup = _keyboard(task, library.has(task.item_id), key in _self_corrected)
        with suppress(TelegramBadRequest):
            await message.edit_reply_markup(reply_markup=markup)


@router.callback_query(AnnotateAct.filter())
async def act(
    cb: CallbackQuery,
    bot: Bot,
    callback_data: AnnotateAct,
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
    match callback_data.act:
        case "fix":
            _fixing[tg] = attempt
            task = await submit.tasks.get(attempt)
            await cb.message.answer(
                t.FIX_ASK.format(bot_heard=escape(task.bot_heard if task else "")),
                reply_markup=_cancel(attempt),
            )
        case "self":
            await _toggle_self_correction(cb.message, tg, attempt, submit, library)
        case "cancel":
            _fixing.pop(tg, None)
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
            _self_corrected.discard((tg, attempt))
            _skipped.setdefault(tg, set()).add(attempt)
            _shown_at.pop((tg, attempt), None)
            await _drop_buttons(cb)
            await _show_next(bot, chat_id, learner, uc, library)
        case "stop":
            _fixing.pop(tg, None)
            await _drop_buttons(cb)
            await cb.message.answer(t.STOPPED)
        case act_name if act_name in _STATUS:
            try:
                saved = await submit.execute(
                    learner, attempt, _STATUS[act_name], seconds_spent=_seconds(tg, attempt),
                    self_corrected=(tg, attempt) in _self_corrected,
                )  # fmt: skip
            except NotAnnotator:  # доступ отозвали, пока запись была на экране
                await cb.answer()
                return
            except LabelError as error:  # «сам исправился» у плохой записи или чужого текста
                await cb.answer(str(error), show_alert=True)
                return
            _self_corrected.discard((tg, attempt))
            await _drop_buttons(cb)
            await cb.message.answer(t.SAVED if saved else t.GONE)
            await _show_next(bot, chat_id, learner, uc, library)
    await cb.answer()

"""Эталон «как правильно» (послушать, учитель записывает) и жалоба «Бот ошибся» (FR-23)."""

import logging
from contextlib import suppress
from typing import Final
from uuid import UUID

from aiogram import Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from dishka import FromDishka

from muallim.application.use_cases.reference import GetReferenceAudio, RecordReference
from muallim.application.use_cases.reports import ReportMistake
from muallim.application.use_cases.settings import GetSettings
from muallim.domain.curriculum import Curriculum
from muallim.domain.learner import Learner
from muallim.domain.report import ReportReason
from muallim.domain.settings import LearnerSettings
from muallim.presentation.telegram import keyboards, texts, views
from muallim.presentation.telegram.callbacks import Dispute, DisputeReason, Listen
from muallim.presentation.telegram.callbacks import RecordReference as RecordCallback
from muallim.presentation.telegram.display import Display, drop_sound, message_of
from muallim.presentation.telegram.screens import Screen

logger: Final = logging.getLogger(__name__)
router: Final = Router(name="learner.reference")

RECORDING: Final = "recording"  # ключ FSM: карточка, для которой учитель записывает эталон


async def take_recording(state: FSMContext) -> str | None:
    """Карточка, для которой ждём эталон; ожидание снимается — эталоном станет одно голосовое."""
    item_id = (await state.get_data()).get(RECORDING)
    if item_id is not None:
        await state.update_data({RECORDING: None})
    return item_id if isinstance(item_id, str) else None


async def send_reference(msg: Message, item_id: str, audio: bytes) -> Message:
    """Эталон отдельным сообщением: OGG (учитель, готовые записи) — голосовое, аят — аудио (mp3)."""
    if audio[:4] == b"OggS":
        return await msg.answer_voice(BufferedInputFile(audio, filename=f"{item_id}.ogg"))
    return await msg.answer_audio(
        BufferedInputFile(audio, filename=f"{item_id}.mp3"),
        title=texts.RECITER_TITLE,
        performer="EveryAyah",
    )


async def show_card(
    msg: Message,
    display: Display,
    screen: Screen,
    *,
    learner: Learner,
    item_id: str,
    has_audio: bool,
    view: LearnerSettings,
    reference: GetReferenceAudio,
) -> None:
    """Показать карточку; с «автозвуком» эталон приходит сам — над карточкой (ADR-0061).

    Telegram не собирает картинку, звук и кнопки в одно сообщение, поэтому со звуком карточка —
    новым сообщением под голосовым, прежний экран убирается. Прошлое автоголосовое удаляется.
    """
    bot = msg.bot
    assert bot is not None  # noqa: S101
    await display.drop_sound(bot, msg.chat.id)
    audio = None
    if view.auto_reference and has_audio:
        audio = await reference.execute(learner, item_id, auto=True)
    if audio is None:
        await display.show(msg, screen)
        return
    with suppress(TelegramBadRequest):
        await msg.delete()
    try:
        sound = await send_reference(msg, item_id, audio)
    except TelegramAPIError:  # звук не ушёл — карточка всё равно нужна (ревью круга 3)
        logger.warning("Автозвук не отправлен", exc_info=True)
    else:
        display.keep_sound(msg.chat.id, sound.message_id)
    await display.send(bot, msg.chat.id, screen)


@router.callback_query(Listen.filter())
async def cb_listen(
    cb: CallbackQuery,
    callback_data: Listen,
    learner: FromDishka[Learner],
    uc: FromDishka[GetReferenceAudio],
    display: FromDishka[Display],
    learner_settings: FromDishka[GetSettings],
) -> None:
    """С автозвуком эталон над карточкой — один: новый заменяет прежний (TD-FN-93 п. 2)."""
    audio = await uc.execute(learner, callback_data.item_id)
    if audio is None:
        await cb.answer(texts.NO_REFERENCE, show_alert=True)
        return
    if msg := message_of(cb):
        sound = await send_reference(msg, callback_data.item_id, audio)
        if (await learner_settings.execute(learner)).auto_reference:
            await drop_sound(display, msg)
            display.keep_sound(msg.chat.id, sound.message_id)
    await cb.answer()


@router.callback_query(RecordCallback.filter())
async def cb_record(
    cb: CallbackQuery,
    callback_data: RecordCallback,
    state: FSMContext,
    learner: FromDishka[Learner],
    recorder: FromDishka[RecordReference],
    cur: FromDishka[Curriculum],
) -> None:
    if not recorder.allowed(learner):
        await cb.answer()
        return
    await state.update_data({RECORDING: callback_data.item_id})
    if msg := message_of(cb):
        item = cur.item(callback_data.item_id)
        await msg.answer(texts.RECORD_ASK.format(text=item.text, item=item.id))
    await cb.answer()


@router.callback_query(Dispute.filter())
async def cb_dispute(cb: CallbackQuery, callback_data: Dispute) -> None:
    code = views.attempt_code(UUID(hex=callback_data.attempt))
    if msg := message_of(cb):
        await msg.answer(
            texts.DISPUTE_ASK.format(code=code),
            reply_markup=keyboards.dispute_reasons(callback_data.attempt),
        )
    await cb.answer()


@router.callback_query(DisputeReason.filter())
async def cb_dispute_reason(
    cb: CallbackQuery,
    callback_data: DisputeReason,
    learner: FromDishka[Learner],
    uc: FromDishka[ReportMistake],
) -> None:
    if callback_data.reason == keyboards.CANCEL:  # «Отмена»: убрать меню, жалобы нет
        if msg := message_of(cb):
            with suppress(TelegramAPIError):
                await msg.delete()
        await cb.answer()
        return
    try:
        attempt_id, reason = UUID(hex=callback_data.attempt), ReportReason(callback_data.reason)
    except ValueError:
        await cb.answer(texts.DISPUTE_FAILED, show_alert=True)
        return
    ok = await uc.execute(learner, attempt_id, reason)
    if msg := message_of(cb):
        await msg.edit_text(texts.DISPUTE_THANKS if ok else texts.DISPUTE_FAILED)
    await cb.answer()

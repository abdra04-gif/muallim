"""Эталон «как правильно» (послушать, учитель записывает) и жалоба «Бот ошибся» (FR-23)."""

from typing import Final
from uuid import UUID

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery
from dishka import FromDishka

from muallim.application.use_cases.reference import GetReferenceAudio, RecordReference
from muallim.application.use_cases.reports import ReportMistake
from muallim.domain.curriculum import Curriculum
from muallim.domain.learner import Learner
from muallim.domain.report import ReportReason
from muallim.presentation.telegram import keyboards, texts, views
from muallim.presentation.telegram.callbacks import Dispute, DisputeReason, Listen
from muallim.presentation.telegram.callbacks import RecordReference as RecordCallback
from muallim.presentation.telegram.display import message_of

router: Final = Router(name="learner.reference")

RECORDING: Final = "recording"  # ключ FSM: карточка, для которой учитель записывает эталон


async def take_recording(state: FSMContext) -> str | None:
    """Карточка, для которой ждём эталон; ожидание снимается — эталоном станет одно голосовое."""
    item_id = (await state.get_data()).get(RECORDING)
    if item_id is not None:
        await state.update_data({RECORDING: None})
    return item_id if isinstance(item_id, str) else None


@router.callback_query(Listen.filter())
async def cb_listen(
    cb: CallbackQuery,
    callback_data: Listen,
    learner: FromDishka[Learner],
    uc: FromDishka[GetReferenceAudio],
) -> None:
    audio = await uc.execute(learner, callback_data.item_id)
    if audio is None:
        await cb.answer(texts.NO_REFERENCE, show_alert=True)
        return
    if msg := message_of(cb):
        name = callback_data.item_id
        if audio[:4] == b"OggS":  # запись учителя — голосовое
            await msg.answer_voice(BufferedInputFile(audio, filename=f"{name}.ogg"))
        else:  # чтение Хусари (mp3)
            await msg.answer_audio(
                BufferedInputFile(audio, filename=f"{name}.mp3"),
                title=texts.RECITER_TITLE,
                performer="EveryAyah",
            )
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
    try:
        attempt_id, reason = UUID(hex=callback_data.attempt), ReportReason(callback_data.reason)
    except ValueError:
        await cb.answer(texts.DISPUTE_FAILED, show_alert=True)
        return
    ok = await uc.execute(learner, attempt_id, reason)
    if msg := message_of(cb):
        await msg.edit_text(texts.DISPUTE_THANKS if ok else texts.DISPUTE_FAILED)
    await cb.answer()

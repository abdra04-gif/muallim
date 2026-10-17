"""Обработчики Telegram. Тонкие: разобрать апдейт → вызвать сценарий → показать экран.

Навигация (ADR-0024): кнопки меняют одно и то же сообщение на месте (show → edit), поэтому чат не
растёт и не уезжает вниз. Новое сообщение — только для /команд и результата голосового; у
предыдущего экрана кнопки убираются, чтобы не путаться.
"""

import io
import logging
import random
from contextlib import suppress
from typing import Final
from uuid import UUID

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InaccessibleMessage,
    InputMediaPhoto,
    Message,
)
from dishka import FromDishka

from muallim.application.ports.recognition import RecognitionError
from muallim.application.ports.storage import ReferenceAudioLibrary
from muallim.application.use_cases.cards import OpenItem
from muallim.application.use_cases.learners import DeleteMyData, SetResearchConsent
from muallim.application.use_cases.progress import GetProgress
from muallim.application.use_cases.quiz import PracticeQuiz
from muallim.application.use_cases.reading import HowToRead
from muallim.application.use_cases.recitation import AssessRecitation
from muallim.application.use_cases.reference import GetReferenceAudio, RecordReference
from muallim.application.use_cases.reports import ReportMistake
from muallim.domain.curriculum import Curriculum
from muallim.domain.learner import Learner
from muallim.domain.report import ReportReason
from muallim.presentation.telegram import keyboards, screens, texts, views
from muallim.presentation.telegram.callbacks import (
    Again,
    Consent,
    DeleteData,
    Dispute,
    DisputeReason,
    GoItem,
    Help,
    Home,
    Lessons,
    Listen,
    Menu,
    Noop,
    Privacy,
    Quiz,
    QuizAnswer,
    ShowProgress,
    Signs,
)
from muallim.presentation.telegram.callbacks import (
    RecordReference as RecordCallback,
)
from muallim.presentation.telegram.learner import NewLearner
from muallim.presentation.telegram.screens import Screen

logger: Final = logging.getLogger(__name__)
router: Final = Router(name="learner")

# Память процесса (сбрасывается при перезапуске — это не данные исследования):
_file_ids: dict[str, str] = {}  # ключ картинки → Telegram file_id (не загружать заново)
_last_screen: dict[int, int] = {}  # чат → сообщение текущего экрана
_recording: dict[int, str] = {}  # учитель → карточка, для которой ждём эталон


def _message(cb: CallbackQuery) -> Message | None:
    msg = cb.message
    return None if msg is None or isinstance(msg, InaccessibleMessage) else msg


# ---------- показ экранов ----------
def _photo(screen: Screen) -> str | BufferedInputFile:
    assert screen.image is not None  # noqa: S101
    cached = _file_ids.get(screen.image_key) if screen.image_key else None
    return cached or BufferedInputFile(screen.image, filename="screen.png")


def _remember(screen: Screen, msg: Message) -> None:
    if screen.image_key and msg.photo:
        _file_ids[screen.image_key] = msg.photo[-1].file_id


async def _retire(bot: Bot, chat_id: int, new_id: int) -> None:
    old = _last_screen.get(chat_id)
    _last_screen[chat_id] = new_id
    if old and old != new_id:
        with suppress(TelegramBadRequest):  # сообщение удалено или уже без кнопок
            await bot.edit_message_reply_markup(chat_id=chat_id, message_id=old, reply_markup=None)


async def send(bot: Bot, chat_id: int, screen: Screen) -> Message:
    """Экран — одним сообщением; с ``details`` — двумя, кнопки у второго (оно и есть экран)."""
    keyboard = None if screen.details else screen.keyboard
    if screen.image is not None:
        msg = await bot.send_photo(
            chat_id, _photo(screen), caption=screen.caption, reply_markup=keyboard
        )
        _remember(screen, msg)
    else:
        msg = await bot.send_message(chat_id, screen.caption, reply_markup=keyboard)
    if screen.details:
        msg = await bot.send_message(chat_id, screen.details, reply_markup=screen.keyboard)
    await _retire(bot, chat_id, msg.message_id)
    return msg


async def show(msg: Message, screen: Screen) -> None:
    """Заменить экран в том же сообщении; если тип не совпадает — новое сообщение вместо старого."""
    bot = msg.bot
    assert bot is not None  # noqa: S101
    if screen.details:  # экран из двух сообщений на месте одного не показать
        with suppress(TelegramBadRequest):
            await msg.delete()
        await send(bot, msg.chat.id, screen)
        return
    try:
        if screen.image is not None and msg.photo:
            media = InputMediaPhoto(media=_photo(screen), caption=screen.caption, parse_mode="HTML")
            edited = await msg.edit_media(media, reply_markup=screen.keyboard)
            if isinstance(edited, Message):
                _remember(screen, edited)
            _last_screen[msg.chat.id] = msg.message_id
            return
        if screen.image is None and msg.text:
            await msg.edit_text(screen.caption, reply_markup=screen.keyboard)
            _last_screen[msg.chat.id] = msg.message_id
            return
    except TelegramBadRequest as error:
        if "not modified" in str(error):
            return
        logger.info("Экран не изменить на месте (%s) — отправляю заново", error)
    with suppress(TelegramBadRequest):
        await msg.delete()
    await send(bot, msg.chat.id, screen)


# ---------- команды ----------
@router.message(CommandStart())
async def start(
    m: Message,
    bot: Bot,
    learner: FromDishka[Learner],
    is_new: FromDishka[NewLearner],
    cur: FromDishka[Curriculum],
    progress: FromDishka[GetProgress],
) -> None:
    if is_new and not learner.research_consent:
        await m.answer(texts.WELCOME)
        await m.answer(texts.CONSENT_TEXT, reply_markup=keyboards.consent())
        return
    await send(bot, m.chat.id, screens.home(cur, await progress.execute(learner)))


@router.message(Command("lessons"))
async def lessons(
    m: Message,
    bot: Bot,
    learner: FromDishka[Learner],
    cur: FromDishka[Curriculum],
    progress: FromDishka[GetProgress],
) -> None:
    await send(bot, m.chat.id, screens.lessons(cur, await progress.execute(learner), part=-1))


@router.message(Command("progress"))
async def progress_cmd(
    m: Message,
    bot: Bot,
    learner: FromDishka[Learner],
    cur: FromDishka[Curriculum],
    progress: FromDishka[GetProgress],
) -> None:
    await send(bot, m.chat.id, screens.progress(cur, await progress.execute(learner)))


@router.message(Command("help"))
async def help_cmd(m: Message, bot: Bot) -> None:
    await send(bot, m.chat.id, screens.help_screen())


@router.message(Command("privacy"))
async def privacy(m: Message, bot: Bot, learner: FromDishka[Learner]) -> None:
    await send(bot, m.chat.id, screens.privacy(learner.research_consent))


@router.message(Command("signs"))
async def signs_cmd(m: Message, bot: Bot) -> None:
    await send(bot, m.chat.id, screens.signs())


@router.message(Command("quiz"))
async def quiz_cmd(
    m: Message, bot: Bot, learner: FromDishka[Learner], uc: FromDishka[PracticeQuiz]
) -> None:
    q = await uc.next(learner, random.randrange(10**6))  # noqa: S311
    await send(bot, m.chat.id, screens.quiz(q) if q else screens.quiz_unavailable())


@router.message(Command("me"))
async def me(m: Message, learner: FromDishka[Learner]) -> None:
    await m.answer(views.me(learner.pseudonym))


# ---------- навигация ----------
@router.callback_query(Home.filter())
@router.callback_query(Menu.filter())  # кнопки из старых сообщений
async def cb_home(
    cb: CallbackQuery,
    learner: FromDishka[Learner],
    cur: FromDishka[Curriculum],
    progress: FromDishka[GetProgress],
) -> None:
    if msg := _message(cb):
        await show(msg, screens.home(cur, await progress.execute(learner)))
    await cb.answer()


@router.callback_query(Lessons.filter())
async def cb_lessons(
    cb: CallbackQuery,
    callback_data: Lessons,
    learner: FromDishka[Learner],
    cur: FromDishka[Curriculum],
    progress: FromDishka[GetProgress],
) -> None:
    if msg := _message(cb):
        screen = screens.lessons(
            cur, await progress.execute(learner), callback_data.part, callback_data.page
        )
        await show(msg, screen)
    await cb.answer()


@router.callback_query(ShowProgress.filter())
async def cb_progress(
    cb: CallbackQuery,
    learner: FromDishka[Learner],
    cur: FromDishka[Curriculum],
    progress: FromDishka[GetProgress],
) -> None:
    if msg := _message(cb):
        await show(msg, screens.progress(cur, await progress.execute(learner)))
    await cb.answer()


@router.callback_query(Help.filter())
async def cb_help(cb: CallbackQuery) -> None:
    if msg := _message(cb):
        await show(msg, screens.help_screen())
    await cb.answer()


@router.callback_query(Signs.filter())
async def cb_signs(cb: CallbackQuery) -> None:
    if msg := _message(cb):
        await show(msg, screens.signs())
    await cb.answer()


@router.callback_query(Quiz.filter())
async def cb_quiz(
    cb: CallbackQuery, learner: FromDishka[Learner], uc: FromDishka[PracticeQuiz]
) -> None:
    q = await uc.next(learner, random.randrange(10**6))  # noqa: S311
    if msg := _message(cb):
        await show(msg, screens.quiz(q) if q else screens.quiz_unavailable())
    await cb.answer()


@router.callback_query(QuizAnswer.filter())
async def cb_quiz_answer(
    cb: CallbackQuery,
    callback_data: QuizAnswer,
    learner: FromDishka[Learner],
    uc: FromDishka[PracticeQuiz],
) -> None:
    data = callback_data
    try:
        q = await uc.answer(learner, data.i, data.v, data.s, data.p)
    except (KeyError, IndexError):
        await cb.answer(texts.STALE_BUTTON, show_alert=True)
        return
    if msg := _message(cb):
        await show(msg, screens.quiz_answer(q, data.p))
    await cb.answer("✅" if data.p == q.answer else "❌")


@router.callback_query(Privacy.filter())
async def cb_privacy(cb: CallbackQuery, learner: FromDishka[Learner]) -> None:
    if msg := _message(cb):
        await show(msg, screens.privacy(learner.research_consent))
    await cb.answer()


@router.callback_query(GoItem.filter())
async def cb_go(
    cb: CallbackQuery,
    callback_data: GoItem,
    learner: FromDishka[Learner],
    uc: FromDishka[OpenItem],
    cur: FromDishka[Curriculum],
    library: FromDishka[ReferenceAudioLibrary],
    recorder: FromDishka[RecordReference],
    reading: FromDishka[HowToRead],
) -> None:
    try:
        item = await uc.execute(learner, callback_data.item_id)
    except KeyError:
        await cb.answer(texts.STALE_BUTTON, show_alert=True)
        return
    if msg := _message(cb):
        screen = screens.card(
            cur,
            item,
            library.has(item.id),
            recorder.allowed(learner),
            reading.execute(learner, item),
        )
        await show(msg, screen)
    await cb.answer()


@router.callback_query(Noop.filter())
async def cb_noop(cb: CallbackQuery) -> None:
    await cb.answer()


@router.callback_query(Again.filter())  # кнопки «Ещё раз» из старых сообщений
async def cb_again(cb: CallbackQuery) -> None:
    await cb.answer(texts.RECORD_AGAIN)


# ---------- согласие и данные ----------
@router.callback_query(Consent.filter())
async def cb_consent(
    cb: CallbackQuery,
    callback_data: Consent,
    learner: FromDishka[Learner],
    uc: FromDishka[SetResearchConsent],
    cur: FromDishka[Curriculum],
    progress: FromDishka[GetProgress],
) -> None:
    await uc.execute(learner, callback_data.granted)
    await cb.answer(texts.CONSENT_SAVED_YES if callback_data.granted else texts.CONSENT_SAVED_NO)
    if msg := _message(cb):
        screen = (
            screens.privacy(learner.research_consent)
            if callback_data.then == "privacy"
            else screens.home(cur, await progress.execute(learner))
        )
        await show(msg, screen)


@router.callback_query(DeleteData.filter(F.confirmed.is_(False)))
async def cb_delete_ask(cb: CallbackQuery) -> None:
    if msg := _message(cb):
        await show(msg, Screen(texts.DELETE_CONFIRM, keyboards.delete_confirm()))
    await cb.answer()


@router.callback_query(DeleteData.filter(F.confirmed.is_(True)))
async def cb_delete(
    cb: CallbackQuery, learner: FromDishka[Learner], uc: FromDishka[DeleteMyData]
) -> None:
    await uc.execute(learner)
    if msg := _message(cb):
        await msg.edit_text(texts.DELETE_DONE)
    await cb.answer()


# ---------- эталон и жалобы ----------
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
    if msg := _message(cb):
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
    learner: FromDishka[Learner],
    recorder: FromDishka[RecordReference],
    cur: FromDishka[Curriculum],
) -> None:
    if not recorder.allowed(learner):
        await cb.answer()
        return
    _recording[learner.telegram_user_id] = callback_data.item_id
    if msg := _message(cb):
        item = cur.item(callback_data.item_id)
        await msg.answer(texts.RECORD_ASK.format(text=item.text, item=item.id))
    await cb.answer()


@router.callback_query(Dispute.filter())
async def cb_dispute(cb: CallbackQuery, callback_data: Dispute) -> None:
    code = views.attempt_code(UUID(hex=callback_data.attempt))
    if msg := _message(cb):
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
    if msg := _message(cb):
        await msg.edit_text(texts.DISPUTE_THANKS if ok else texts.DISPUTE_FAILED)
    await cb.answer()


# ---------- голосовые ----------
@router.message(F.voice)
async def on_voice(
    m: Message,
    bot: Bot,
    learner: FromDishka[Learner],
    uc: FromDishka[AssessRecitation],
    cards: FromDishka[OpenItem],
    library: FromDishka[ReferenceAudioLibrary],
    recorder: FromDishka[RecordReference],
    cur: FromDishka[Curriculum],
) -> None:
    assert m.voice is not None  # гарантирует фильтр F.voice  # noqa: S101
    if m.voice.duration < 1:
        await m.reply(texts.VOICE_TOO_SHORT)
        return
    buf = io.BytesIO()
    await bot.download(m.voice, destination=buf)

    item_id = _recording.pop(learner.telegram_user_id, None)
    if item_id is not None and await recorder.execute(learner, item_id, buf.getvalue()):
        await m.reply(texts.RECORD_SAVED.format(item=item_id))
        return

    item = cards.current(learner)
    if not item.is_practice:
        await m.reply(texts.NOT_PRACTICE)
        return
    wait = await m.reply(texts.LISTENING.format(item=item.text))
    try:
        result = await uc.execute(learner, buf.getvalue())
    except RecognitionError:
        logger.warning("Не удалось распознать запись ученика %s", learner.pseudonym, exc_info=True)
        await wait.edit_text(texts.CANT_PROCESS)
        return
    await wait.delete()
    await send(bot, m.chat.id, screens.result(cur, result, library.has(result.item.id)))


@router.message()
async def fallback(
    m: Message,
    bot: Bot,
    learner: FromDishka[Learner],
    cur: FromDishka[Curriculum],
    progress: FromDishka[GetProgress],
) -> None:
    await m.answer(texts.SEND_VOICE)
    await send(bot, m.chat.id, screens.home(cur, await progress.execute(learner)))

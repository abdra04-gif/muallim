from aiogram.filters.callback_data import CallbackData


class GoItem(CallbackData, prefix="go"):
    item_id: str


class Home(CallbackData, prefix="home"):
    """Главный экран."""


class Menu(CallbackData, prefix="menu"):
    """Устаревшая кнопка «Уроки» из сообщений до v0.5 — ведёт на главный экран."""


class Lessons(CallbackData, prefix="lessons"):
    part: int = -1  # -1 — список частей книги
    page: int = 0


class Signs(CallbackData, prefix="signs"):
    """Знаки огласовки."""


class Quiz(CallbackData, prefix="quiz"):
    """Следующий вопрос закрепления."""


class QuizAnswer(CallbackData, prefix="qa"):
    i: str  # id карточки-буквы
    v: int  # огласовка
    s: int  # seed вопроса
    p: int  # выбранный вариант


class Help(CallbackData, prefix="help"):
    pass


class Privacy(CallbackData, prefix="privacy"):
    pass


class RecordReference(CallbackData, prefix="record"):
    """Режим учителя: следующее голосовое станет эталоном этой карточки."""

    item_id: str


class ShowProgress(CallbackData, prefix="progress"):
    pass


class Consent(CallbackData, prefix="consent"):
    granted: bool
    then: str = "home"  # куда вернуться: home — после /start, privacy — со страницы данных


class Profile(CallbackData, prefix="pf"):
    """Ответы анкеты копятся в кнопке: пустое поле — вопрос ещё не задан (FR-44)."""

    adult: bool
    lang: str = ""
    read: str = ""


class DeleteData(CallbackData, prefix="delete"):
    confirmed: bool


class Noop(CallbackData, prefix="noop"):
    pass


class Again(CallbackData, prefix="again"):
    pass


class Listen(CallbackData, prefix="listen"):
    item_id: str


class Dispute(CallbackData, prefix="dispute"):
    attempt: str  # UUID.hex — 32 символа, укладывается в лимит 64 байта


class DisputeReason(CallbackData, prefix="dreason"):
    attempt: str
    reason: str


class AnnotateAct(CallbackData, prefix="ann"):
    """Разметчик (FR-17): ok — бот прав, fix — исправить, bad — плохая запись, off — читал не то,
    skip — пропустить, stop — закончить, cancel — отменить исправление, ref — эталон."""

    a: str  # UUID.hex попытки — 32 символа
    act: str


class Opening(CallbackData, prefix="open"):
    """Начало занятия (ADR-0050): ``start`` — читать истиазу и басмалу, ``skip`` — пропустить."""

    act: str


class ShareLesson(CallbackData, prefix="share"):
    """«📤 Поделиться» — прислать открытку пройденного урока для пересылки (ADR-0050)."""

    lesson: str

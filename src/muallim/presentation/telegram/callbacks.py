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


class LettersSheet(CallbackData, prefix="sheet"):
    """Шпаргалка букв по книге до урока (FR-52, ADR-0062 п. 7). ``item_id`` — карточка, с которой
    открыли («◀️ Назад» на неё); пусто — открыли с «🔤 Знаки»."""

    lesson_id: str
    item_id: str = ""


class Quiz(CallbackData, prefix="quiz"):
    """Открытый или следующий вопрос закрепления (новый раунд — после итога)."""


class QuizAnswer(CallbackData, prefix="qa"):
    """Ответ на вопрос закрепления (ADR-0066): вопрос и варианты — в строке ``quiz_answers``."""

    a: str  # id строки quiz_answers (UUID.hex)
    p: int  # выбранный вариант


class QuizSkip(CallbackData, prefix="qs"):
    """«Не могу сейчас говорить / слушать» на ступенях ②③ (ADR-0066, как в Duolingo)."""

    a: str  # id строки quiz_answers (UUID.hex)


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


class ShowSettings(CallbackData, prefix="settings"):
    """⚙️ Настройки ученика (FR-51, ADR-0061): ``page`` пусто — экран настроек, ``reminder`` —
    выбор часа напоминания, ``hint`` — подсказка к заголовку «Как читается» (TD-FN-93 п. 5)."""

    page: str = ""


class ChangeSetting(CallbackData, prefix="set"):
    """Поставить настройке значение явно (не «переключить»): повторное нажатие старой кнопки
    ничего не ломает. ``value`` — ``true``/``false``, значение ``HowToRead``, минута суток или
    смещение от UTC в минутах (``off`` — выключить напоминание)."""

    name: str
    value: str


class Me(CallbackData, prefix="me"):
    """«🪪 Мой ID» — псевдоним ученика, как /me."""

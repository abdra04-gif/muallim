"""Тексты разметчику в Telegram (FR-17). Черновик агента — утвердить автору.

Разметчик — преподаватель или уверенно читающий студент, не ученик: тексты короче и прямее,
термины руководства (docs/data/annotation-guide.md) сохранены. Кто ученик — не показываем.
"""

from typing import Final

TASK: Final = (
    "📝 <b>Разметка</b> · {annotator} · осталось {remaining}\n"
    "{where}\n\n"
    "<b>{item_text}</b>\n\n"
    "Бот: {verdict}\n"
    "{errors}"
    "Бот услышал: <code>{bot_heard}</code>\n"
    "Как должно звучать: <code>{reference}</code>\n"
    "{learner}"
    "\nПослушайте запись выше и проверьте ответ бота."
)
WHERE: Final = "Стр. {page}, строка {line} · карточка {item}"
WHERE_ITEM: Final = "Карточка {item}"
VERDICT_PASSED: Final = "✅ засчитано"
VERDICT_FAILED: Final = "❌ не засчитано"
ERRORS: Final = "Ошибки бота: {errors}\n"
NO_ERRORS: Final = "Ошибок бот не нашёл\n"
LEARNER_SAYS: Final = "⚠️ Ученик оспорил: {reason}\n"
LEARNER_REASONS: Final = {
    "read_correctly": "«я прочитал правильно»",
    "wrong_error": "«ошибка указана не та»",
    "other": "«бот ошибся»",
}

BTN_OK: Final = "✅ Бот прав"
BTN_FIX: Final = "✏️ Бот ошибся — исправить"
BTN_SELF: Final = "🔁 Сам исправился"  # ученик ошибся и сам перечитал верно (руководство 2.1)
BTN_SELF_ON: Final = "🔁 Сам исправился ✓"
BTN_BAD: Final = "🔇 Плохая запись"
BTN_OFF: Final = "🙅 Читал не то"
BTN_SKIP: Final = "⏭ Пропустить"
BTN_STOP: Final = "⏹ Закончить"
BTN_REF: Final = "🔊 Как правильно"
BTN_CANCEL: Final = "↩️ Отмена"

FIX_ASK: Final = (
    "✏️ Пришлите сообщением, что прозвучало <b>на самом деле</b>, фонетическими знаками.\n"
    "Скопируйте, что услышал бот, и исправьте:\n<code>{bot_heard}</code>\n\n"
    "Хамза — всегда «ء»; удвоение — две одинаковые буквы, без шадды; сукун не пишется; "
    "долгие — «ا», «ۦ», «ۥ»."
)
FIX_WRONG: Final = "⚠️ {error}.\nИсправьте и пришлите ещё раз — или «↩️ Отмена»."
SAVED: Final = "✅ Сохранено"
GONE: Final = "Эту запись уже нельзя размечать: ученик удалил данные или отозвал согласие."
DONE: Final = "🎉 Всё размечено — новых записей нет. Спасибо!"
STOPPED: Final = "⏹ Закончили. Продолжить — /annotate"
NO_REFERENCE: Final = "Для этой карточки эталона нет"

INVITE_OK: Final = "Доступ к разметке открыт: вы — {annotator}."
INVITE_INVALID: Final = "Код не подходит или устарел. Попросите новый у исследователя."
INVITE_LOCKED: Final = "Слишком много неверных кодов. Попробуйте через час."

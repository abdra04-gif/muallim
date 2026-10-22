"""Тексты ученику — только в текстовых модулях; кнопки в лимите Telegram (TD-FN-57, TD-FN-58).

Тексты ученику и согласие — зона человека (CLAUDE.md), хук `human_zones` защищает `texts.py`.
Строка, оставленная в `keyboards.py` или `screens.py`, правится без вопроса — так было с кнопками
согласия до 2026-10-18.
"""

import ast
import inspect
import re
from pathlib import Path

import pytest
from aiogram.filters.callback_data import CallbackData

from muallim.domain.curriculum import Curriculum
from muallim.domain.settings import HowToRead
from muallim.presentation.telegram import callbacks, texts

ROOT = Path(__file__).resolve().parents[2]
PRESENTATION = ROOT / "src" / "muallim" / "presentation"
TEXT_MODULES = {"texts.py", "annotator_texts.py"}
CYRILLIC = re.compile("[А-Яа-яЁё]")
LOG_METHODS = {"debug", "info", "warning", "error", "exception", "critical"}

# Кириллица, которую ученик не видит: сравнение с заметками программы (curriculum/), не вывод.
NOT_SHOWN = {("screens.py", "фраза"), ("screens.py", "сура"), ("screens.py", "басмала"),
             ("screens.py", "слог")}  # fmt: skip

pytestmark = pytest.mark.architecture

# настройки ученика, которые меняются кнопками экрана ⚙️ (FR-51)
_SETTING_NAMES = (
    "how_to_read", "auto_reference", "daily_opening", "large_font", "research_block",
    "reminder_minute", "utc_offset_min",  # круг 4: напоминание и «который у тебя час?»
)  # fmt: skip


def _shown_strings(path: Path) -> list[tuple[int, str]]:
    """Строковые литералы с кириллицей, кроме docstring, сообщений журнала и исключений."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    hidden: set[int] = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr):
            hidden.add(id(body[0].value))  # docstring
        is_log = (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in LOG_METHODS
        )
        if is_log or isinstance(node, ast.Raise):
            hidden |= {id(sub) for sub in ast.walk(node)}
    return [
        (node.lineno, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and CYRILLIC.search(node.value)
        and id(node) not in hidden
        and (path.name, node.value) not in NOT_SHOWN
    ]


def test_learner_texts_only_in_text_modules() -> None:
    found = [
        f"{path.relative_to(ROOT)}:{line}: {value!r}"
        for path in sorted(PRESENTATION.rglob("*.py"))
        if path.name not in TEXT_MODULES
        for line, value in _shown_strings(path)
    ]
    assert not found, "тексты ученику вне texts.py (зона человека):\n" + "\n".join(found)


def _worst_cases(curriculum: Curriculum) -> dict[type[CallbackData], CallbackData]:
    """Самые длинные значения полей, которые бот может положить в кнопку."""
    item = max((i.id for lesson in curriculum.lessons for i in lesson.items), key=len)
    attempt = "f" * 32  # UUID.hex
    reason = max(texts.DISPUTE_REASONS, key=len)
    big = 10**6  # seed вопроса: random.randrange(10**6)
    setting = max(_SETTING_NAMES, key=len)
    value = max([*(str(h) for h in HowToRead), "true", "false", "-720", "1439"], key=len)
    return {
        callbacks.GoItem: callbacks.GoItem(item_id=item),
        callbacks.Home: callbacks.Home(),
        callbacks.Menu: callbacks.Menu(),
        callbacks.Lessons: callbacks.Lessons(part=big, page=big),
        callbacks.Signs: callbacks.Signs(),
        callbacks.Quiz: callbacks.Quiz(),
        callbacks.QuizAnswer: callbacks.QuizAnswer(a=attempt, p=big),  # id строки quiz_answers
        callbacks.QuizSkip: callbacks.QuizSkip(a=attempt),  # «Не могу сейчас…» (ADR-0066)
        callbacks.Help: callbacks.Help(),
        callbacks.Privacy: callbacks.Privacy(),
        callbacks.RecordReference: callbacks.RecordReference(item_id=item),
        callbacks.ShowProgress: callbacks.ShowProgress(),
        callbacks.Consent: callbacks.Consent(granted=False, then="privacy"),
        callbacks.Profile: callbacks.Profile(adult=False, lang="other", read="slow_syllables"),
        callbacks.DeleteData: callbacks.DeleteData(confirmed=False),
        callbacks.Noop: callbacks.Noop(),
        callbacks.Again: callbacks.Again(),
        callbacks.Listen: callbacks.Listen(item_id=item),
        callbacks.Dispute: callbacks.Dispute(attempt=attempt),
        callbacks.DisputeReason: callbacks.DisputeReason(attempt=attempt, reason=reason),
        callbacks.AnnotateAct: callbacks.AnnotateAct(a=attempt, act="cancel"),
        callbacks.Opening: callbacks.Opening(act="start"),
        callbacks.ShareLesson: callbacks.ShareLesson(
            lesson=max((les.id for les in curriculum.lessons), key=len)
        ),
        # ⚙️ Настройки (FR-51, ADR-0061): экран, смена значения, «🪪 Мой ID»
        callbacks.ShowSettings: callbacks.ShowSettings(),
        callbacks.ChangeSetting: callbacks.ChangeSetting(name=setting, value=value),
        callbacks.Me: callbacks.Me(),
        # 📋 Шпаргалка букв (FR-52, ADR-0062)
        callbacks.LettersSheet: callbacks.LettersSheet(
            lesson_id=max((les.id for les in curriculum.lessons), key=len), item_id=item
        ),
    }


def test_every_callback_fits_telegram_limit(curriculum: Curriculum) -> None:
    """callback_data ≤ 64 байт (Bot API); aiogram иначе падает уже в работе, у ученика."""
    declared = {
        cls
        for _, cls in inspect.getmembers(callbacks, inspect.isclass)
        if issubclass(cls, CallbackData) and cls is not CallbackData
    }
    cases = _worst_cases(curriculum)
    assert declared == set(cases), f"нет худшего случая для: {declared - set(cases)}"
    for cls, data in cases.items():
        packed = data.pack()
        assert len(packed.encode()) <= 64, f"{cls.__name__}: {len(packed.encode())} байт"


@pytest.mark.parametrize("module", sorted(TEXT_MODULES))
def test_every_text_is_used(module: str) -> None:
    """Мёртвый текст в зоне человека вводит в заблуждение: его правят, а ученик его не видит."""
    path = PRESENTATION / "telegram" / module
    names = [
        target.id
        for node in ast.parse(path.read_text(encoding="utf-8")).body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name) and target.id.isupper()
    ]
    code = "\n".join(
        p.read_text(encoding="utf-8") for p in (ROOT / "src").rglob("*.py") if p != path
    )
    unused = [name for name in names if not re.search(rf"\b{name}\b", code)]
    assert not unused, f"{module}: тексты нигде не используются: {unused}"


def test_texts_are_not_defined_twice() -> None:
    """Второе объявление с тем же именем молча затирает первое (так было с RESULT_HEARD)."""
    tree = ast.parse(Path(texts.__file__).read_text(encoding="utf-8"))
    names: list[str] = []
    for node in tree.body:
        targets = node.targets if isinstance(node, ast.Assign) else []
        if isinstance(node, ast.AnnAssign):
            targets = [node.target]
        names += [t.id for t in targets if isinstance(t, ast.Name)]
    twice = sorted({n for n in names if names.count(n) > 1})
    assert not twice, f"тексты объявлены дважды: {twice}"

"""FR-54 (этап 1): экран результата строится из разбора группами (``RecitationResult.breakdown``).

Решения автора 2026-10-23/24: в тексте не больше двух пунктов; буква урока — первой, словами
«Буква урока …» (у каждой её путаницы — свой пункт; ⭐ убрана — Р6); групп больше — «Ещё K — на
картинке» (только если картинка есть; без картинки — все группы текстом); пункт — «N раз» и «В
словах:» до трёх слов, дальше «…»; каждая строка пункта начинается по-русски; «⏹ Запись
закончилась …» — отдельной строкой вне пунктов; один счётчик «Верно N слов из M» (не при 0 и не у
строки из одного слова); «было → стало» — в процентах, «✨ Исправлено» — по буквам; «👄 Как
сказать», «Нужно / У тебя» по слогам, «Точность» и счёт слогов уходят; значков х̣ с̣ һ ħ θ ʿ ð ’ ‘
нет; экран — одно сообщение, если влезает в подпись; не влезает — ничего не теряется.

Экраны — без Telegram; картинка подменяется (``render.result_marks`` → байты, вызов сверяется с её
сигнатурой), оценка — ``assess``. Строки — из curriculum/course.ru.yaml.
"""

import inspect
from dataclasses import replace
from typing import Any
from uuid import UUID

import pytest

from muallim.application.breakdown import ErrorGroup, build_breakdown
from muallim.application.feedback import FeedbackRenderer
from muallim.application.transcription import plain
from muallim.application.use_cases.recitation import RecitationResult
from muallim.domain.assessment import assess, unread_from
from muallim.domain.attempt import Attempt
from muallim.domain.curriculum import Curriculum, Lexicon, lesson_letter
from muallim.domain.policy import GradingPolicy
from muallim.presentation.telegram import render, screens, texts, views
from tests.fakes import FixedClock

L020_06 = "L020-06"  # صُمْ صِفْ فَصْ صَرَفَ صَبَرَ بَصَرَ — урок ص
L020_06_PHONEMES = "صُمصِففَصصَرَفَصَبَرَبَصَرَ"
L020_02 = "L020-02"  # صَ — одно слово
L024_07 = "L024-07"  # مُحْسِنُ مَحْشَرُ مِنْحَرُ مَحْفَلُ أَحْسَنَ — урок ح
L024_07_PHONEMES = "مُحسِنُمَحشَرُمِنحَرُمَحفَلُءَحسَنَ"
L006_07 = "L006-07"  # إِمْرُ رَمْزُ اِرْمِ مَرْمَرُ رَمْرَمُ زَمْزَمُ — урок م

SWAP_THREE = "سُمْ صِفْ فَصْ سَرَفَ صَبَرَ بَسَرَ"  # ص→س в 1-м, 4-м и 6-м словах
SWAP_ALL = "سُمْ سِفْ فَسْ سَرَفَ سَبَرَ بَسَرَ"  # ص→س во всех шести словах
THREE_KINDS = "سُمْ صِفْ فَصْ صَلَفَ صَبَرَ مَصَرَ"  # ص→س, ر→ل, ب→م
STOPPED = "سُمْ صِفْ فَصْ سَرَفَ"  # остановился после 4-го слова
HA_AND_FATHA = "مُهْسِنُ مَحْشَرُ مِنْهَرُ مَحْفِلُ أَحْسَنَ"  # ح→ه ×2, над ف фатха → кясра

SOUNDS = {"ح": ("ха", "горлом"), "ه": ("ха", "легко"), "ص": ("со", "")}  # автор, Р8 2026-10-24
MARKS = ("х̣", "с̣", "һ", "ħ", "θ", "ʿ", "ð", "’", "‘", "̣", "̱")


@pytest.fixture(scope="module")
def lexicon(curriculum: Curriculum) -> Lexicon:
    return replace(curriculum.lexicon, sounds=SOUNDS)


@pytest.fixture
def drawn(monkeypatch: pytest.MonkeyPatch) -> list[inspect.BoundArguments]:
    """Картинка есть, но не рисуется: вызов ``result_marks`` сверяется с её настоящей сигнатурой."""
    signature = inspect.signature(render.result_marks)
    calls: list[inspect.BoundArguments] = []

    def result_marks(*args: Any, **kwargs: Any) -> bytes:
        calls.append(signature.bind(*args, **kwargs))
        return b"marks.png"

    monkeypatch.setattr(render, "available", lambda: True)
    monkeypatch.setattr(render, "result_marks", result_marks)
    return calls


@pytest.fixture
def no_image(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(render, "available", lambda: False)


def _lesson_letter(c: Curriculum, item_id: str) -> str | None:
    """Буква урока — одна функция домена (её же используют сценарий и экран)."""
    return lesson_letter(c.locate(item_id)[0])


def _result(  # noqa: PLR0917
    c: Curriculum,
    lexicon: Lexicon,
    renderer: FeedbackRenderer,
    item_id: str,
    heard: str,
    reference: str = "",
    *,
    previous: int | None = None,
) -> RecitationResult:
    item = c.item(item_id)
    a = assess(reference or item.text, heard)
    unread = unread_from(a.reference, heard)
    attempt = Attempt(
        UUID(int=1), UUID(int=2), item.id, "v", "stub", a, GradingPolicy().verdict(a),
        None, None, 1, FixedClock().now(),
    )  # fmt: skip
    review = build_breakdown(
        a, item.text, lexicon, unread=unread, lesson_letter=_lesson_letter(c, item_id)
    )
    return RecitationResult(
        item, attempt, renderer.explain(a.errors, a.reference, unread), "", c.next_item(item.id),
        unread_from=unread, previous_score=previous, breakdown=review,
    )  # fmt: skip


def _text(s: screens.Screen) -> str:
    return s.caption + "\n" + s.details


def _point(text: str, n: int) -> str:
    """Пункт № n (с 1): от его номера до следующего номера или до пустой строки (абзаца)."""
    numbers = texts.ERROR_NUMBERS
    assert numbers[n - 1] in text, f"нет пункта {numbers[n - 1]}"
    before, rest = text.split(numbers[n - 1], maxsplit=1)
    lead = before.rsplit("\n", maxsplit=1)[-1]  # то, что стоит перед номером
    for stop in (*numbers[n:], "\n\n"):
        rest = rest.split(stop, maxsplit=1)[0]
    return lead + rest


def _no_marks(text: str) -> None:
    assert not [m for m in MARKS if m in text], [m for m in MARKS if m in text]


def _words_line(g: ErrorGroup) -> str:
    """Слова пункта, как одобрил автор: «مُحْسِنُ «мух-си-ну» · مِنْحَرُ «мин-ха-ру»», до трёх."""
    unique = list({p.word_index: p for p in g.places}.values())[:3]
    shown = [texts.POINT_WORD.format(word=p.word_text, reading=p.word_reading) for p in unique]
    return texts.WORDS_SEPARATOR.join(shown)


def _says(point: str, g: ErrorGroup) -> None:
    """В пункте — «нужно <нужно>», затем «у тебя <у тебя>» (Р6)."""
    need = point.index(f"нужно {g.need_label}")
    assert point.index(f"у тебя {g.heard_label}", need) > need, point


def _russian_first(line: str) -> bool:
    """Первая буква строки (после номера-эмодзи) — кириллица: Telegram не развернёт строку."""
    for number in texts.ERROR_NUMBERS:
        line = line.replace(number, "")
    first = next((ch for ch in line if ch.isalpha()), "")
    return first.lower() in "абвгдеёжзийклмнопрстуфхцчшщъыьэюя" and first != ""


def _words_right(ok: int, total: int) -> str:
    return texts.RESULT_WORDS.format(ok=ok, words=views.plural(ok, texts.WORD_FORMS), total=total)


# ---------- одинаковые ошибки — один пункт ----------
def test_same_swap_in_three_words_is_one_point_with_its_words(
    curriculum: Curriculum, lexicon: Lexicon, renderer: FeedbackRenderer, drawn: list[Any]
) -> None:
    """Баг 1: ص→س в трёх словах — один пункт «3 раза» со словами (раньше третья пропадала)."""
    r = _result(curriculum, lexicon, renderer, L020_06, SWAP_THREE)
    assert r.breakdown is not None
    (g,) = r.breakdown.groups
    text = _text(screens.result(curriculum, r, has_audio=True))
    point = _point(text, 1)
    assert texts.ERROR_NUMBERS[1] not in text
    assert views.times(3) in point
    _says(point, g)
    assert "Буква урока ص" in point  # урок ص
    assert f"В словах: {_words_line(g)}" in point


def test_same_swap_twice_in_one_word_shows_the_word_once(
    curriculum: Curriculum, lexicon: Lexicon, renderer: FeedbackRenderer, drawn: list[Any]
) -> None:
    """Р4: «مَرْمَرُ» → «نَرْنَرُ» — «2 раза», слово в пункте один раз."""
    r = _result(curriculum, lexicon, renderer, L006_07, "إِمْرُ رَمْزُ اِرْمِ نَرْنَرُ رَمْرَمُ زَمْزَمُ")
    assert r.breakdown is not None
    (g,) = r.breakdown.groups
    point = _point(_text(screens.result(curriculum, r, has_audio=True)), 1)
    assert views.times(2) in point
    word = g.places[0]
    assert "В слове:" in point and "В словах:" not in point
    assert point.count(word.word_text) == 1  # «مَرْمَرُ» — один раз, рядом с чтением
    assert texts.POINT_WORD.format(word=word.word_text, reading=word.word_reading) in point


def test_lesson_letter_point_is_first_and_named_in_words(
    curriculum: Curriculum, lexicon: Lexicon, renderer: FeedbackRenderer, drawn: list[Any]
) -> None:
    """Баг 2 (L024-07), вид Р6: «1️⃣ Буква урока ح (Хэ): нужно «ха» горлом, у тебя «ха» легко…
    (2 раза)» и «В словах: …»; «2️⃣ Знак над ف — фатха: нужно «фа», у тебя «фи»» и «В слове: …».
    ⭐ нет (в «Закреплении» ⭐ — «знаю уверенно»); групп две — «Ещё … на картинке» нет."""
    r = _result(curriculum, lexicon, renderer, L024_07, HA_AND_FATHA)
    assert r.breakdown is not None
    letter, vowel = r.breakdown.groups
    text = _text(screens.result(curriculum, r, has_audio=True))
    first, second = _point(text, 1), _point(text, 2)
    assert "⭐" not in text
    name = lexicon.consonants["ح"][0]
    assert f"Буква урока ح ({name})" in first and text.count("Буква урока") == 1
    _says(first, letter)
    assert views.times(2) in first and f"В словах: {_words_line(letter)}" in first
    assert "Знак над ف" in second and "фатха" in second
    _says(second, vowel)
    assert f"В слове: {_words_line(vowel)}" in second
    assert "раз" not in second  # одно место — «(1 раз)» не пишем
    assert "горлом" in first and "легко" in first  # «ха» горлом / «ха» легко
    assert texts.MORE_ON_IMAGE.split("{", maxsplit=1)[0].strip() not in text


def test_two_confusions_of_lesson_letter_both_say_lesson_letter(
    curriculum: Curriculum, lexicon: Lexicon, renderer: FeedbackRenderer, drawn: list[Any]
) -> None:
    """Р4: م→ن и م→ب в уроке م — два первых пункта, оба «Буква урока»; ر→ل — «на картинке»."""
    heard = "إِمْرُ لَمْزُ اِرْمِ نَرْمَرُ رَبْرَمُ زَمْزَمُ"
    r = _result(curriculum, lexicon, renderer, L006_07, heard)
    text = _text(screens.result(curriculum, r, has_audio=True))
    assert "Буква урока" in _point(text, 1) and "Буква урока" in _point(text, 2)
    assert texts.MORE_ON_IMAGE.format(n=1) in text


def test_at_most_two_points_and_the_rest_is_on_the_image(
    curriculum: Curriculum, lexicon: Lexicon, renderer: FeedbackRenderer, drawn: list[Any]
) -> None:
    """Баг 3: три разные замены — в тексте два пункта и «Ещё 1 — на картинке»; третьей подписи
    в тексте нет вовсе."""
    assert views.MAX_ERRORS_SHOWN == 2
    r = _result(curriculum, lexicon, renderer, L020_06, THREE_KINDS)
    assert r.breakdown is not None and len(r.breakdown.groups) == 3
    text = _text(screens.result(curriculum, r, has_audio=True))
    assert texts.ERROR_NUMBERS[1] in text and texts.ERROR_NUMBERS[2] not in text
    assert texts.MORE_ON_IMAGE.format(n=1) in text
    third = r.breakdown.groups[2]
    assert third.need_label not in text and third.heard_label not in text


def test_without_image_every_group_is_in_the_text(
    curriculum: Curriculum, lexicon: Lexicon, renderer: FeedbackRenderer, no_image: None
) -> None:
    """Нет картинки (нет libraqm) — отсылать некуда: все группы текстом, без «на картинке»."""
    r = _result(curriculum, lexicon, renderer, L020_06, THREE_KINDS)
    assert r.breakdown is not None and r.breakdown.groups
    text = _text(screens.result(curriculum, r, has_audio=True))
    for n, g in enumerate(r.breakdown.groups, start=1):
        _says(_point(text, n), g)
    assert "на картинке" not in text
    assert texts.MORE_ON_IMAGE.split("{", maxsplit=1)[0].strip() not in text


def test_group_lists_at_most_three_words(
    curriculum: Curriculum, lexicon: Lexicon, renderer: FeedbackRenderer, drawn: list[Any]
) -> None:
    """ص→س во всех шести словах: «6 раз», первые три слова и «…» — остальные не перечисляются."""
    r = _result(curriculum, lexicon, renderer, L020_06, SWAP_ALL)
    assert r.breakdown is not None
    (g,) = r.breakdown.groups
    assert len(g.places) == 6
    point = _point(_text(screens.result(curriculum, r, has_audio=True)), 1)
    assert views.times(6) in point and "…" in point
    assert _words_line(g) in point  # первые три слова с чтением
    for p in g.places[3:]:
        assert p.word_text not in point and p.word_reading not in point, p.word_text


# ---------- «не дочитано» и крайние случаи ----------
def test_unread_is_its_own_line_outside_the_points(
    curriculum: Curriculum, lexicon: Lexicon, renderer: FeedbackRenderer, drawn: list[Any]
) -> None:
    """«⏹ Запись закончилась на слове … — дочитай до конца, можно медленно» — отдельно (Р6: 📖
    занят «без голоса», «без остановок» пугает новичка); ошибки после остановки — не пункты."""
    r = _result(curriculum, lexicon, renderer, L020_06, STOPPED)
    text = _text(screens.result(curriculum, r, has_audio=True))
    assert texts.ERROR_NUMBERS[0] in text and texts.ERROR_NUMBERS[1] not in text
    assert "📖" not in text
    (line,) = [ln for ln in text.splitlines() if "⏹" in ln]
    assert not any(n in line for n in texts.ERROR_NUMBERS)
    assert "без остановок" not in line and _russian_first(line)
    assert "⏹" not in _point(text, 1)
    assert views.times(2) in _point(text, 1)  # ص→س — 2 раза, а не 3
    _no_marks(line)  # тоже простой кириллицей
    assert plain("صَبَرَ", lexicon) in line  # непрочитанное — простым чтением


def test_only_errors_after_the_stop_show_just_unread(
    curriculum: Curriculum, lexicon: Lexicon, renderer: FeedbackRenderer, drawn: list[Any]
) -> None:
    """Три слова верно и остановка (эталон-фонемы, как в работе): пунктов нет, есть «⏹»."""
    r = _result(curriculum, lexicon, renderer, L020_06, "صُمصِففَص", L020_06_PHONEMES)
    text = _text(screens.result(curriculum, r, has_audio=True))
    assert not any(n in text for n in texts.ERROR_NUMBERS)
    assert "⏹" in text


def test_empty_heard_gives_a_screen_that_fits(
    curriculum: Curriculum, lexicon: Lexicon, renderer: FeedbackRenderer, drawn: list[Any]
) -> None:
    r = _result(curriculum, lexicon, renderer, L020_06, "", L020_06_PHONEMES)
    s = screens.result(curriculum, r, has_audio=True)
    assert len(s.caption) <= screens.CAPTION_LIMIT and texts.ERROR_NUMBERS[0] in _text(s)
    _no_marks(_text(s))


def test_phoneme_reference_gives_the_same_points(
    curriculum: Curriculum, lexicon: Lexicon, renderer: FeedbackRenderer, drawn: list[Any]
) -> None:
    """Эталон — фонемы без пробелов (как от Muaalem): те же пункты, что и с эталоном-текстом."""
    heard = "مُهسِنُمَحشَرُمِنهَرُمَحفِلُءَحسَنَ"
    r = _result(curriculum, lexicon, renderer, L024_07, heard, L024_07_PHONEMES)
    assert r.breakdown is not None
    _, vowel = r.breakdown.groups
    s = screens.result(curriculum, r, has_audio=True)
    first = _point(_text(s), 1)
    assert "Буква урока" in first and views.times(2) in first
    assert vowel.heard_label in _point(_text(s), 2)
    assert _words_right(2, 5) in s.caption
    _no_marks(_text(s))


# ---------- счётчик и то, что уходит с экрана ----------
def test_one_counter_of_right_words(
    curriculum: Curriculum, lexicon: Lexicon, renderer: FeedbackRenderer, drawn: list[Any]
) -> None:
    """Главный счётчик — «Верно 2 слова из 5» в строке вердикта или сразу под ней (одобрено
    автором); «слов верно», «Точность ▰▰ %» и счёт слогов не показываются; на первой попытке
    процентов нет совсем."""
    r = _result(curriculum, lexicon, renderer, L024_07, HA_AND_FATHA)
    s = screens.result(curriculum, r, has_audio=True)
    head = [ln for ln in s.caption.splitlines() if ln.strip()][:2]
    assert any(_words_right(2, 5) in ln for ln in head), head
    assert "слов верно" not in _text(s)
    assert "Точность" not in _text(s) and "слог" not in _text(s)
    assert "%" not in _text(s) and "▰" not in _text(s)
    assert _words_right(2, 5) not in _point(_text(s), 1)


def test_one_word_line_has_no_word_counter(
    curriculum: Curriculum, lexicon: Lexicon, renderer: FeedbackRenderer, drawn: list[Any]
) -> None:
    """«صَ» → «سَ»: «верно 0 слов из 1» — бессмыслица; разбор при этом есть."""
    r = _result(curriculum, lexicon, renderer, L020_02, "سَ")
    s = screens.result(curriculum, r, has_audio=True)
    assert "из 1" not in _text(s) and "Верно 0" not in _text(s)
    assert texts.ERROR_NUMBERS[0] in _text(s)


def test_result_has_no_how_to_say_or_syllable_comparison(
    curriculum: Curriculum, lexicon: Lexicon, renderer: FeedbackRenderer, drawn: list[Any]
) -> None:
    """«👄 Как сказать», «Нужно: / У тебя:» по слогам и значки х̣ һ ħ ’ — не для новичка с нуля."""
    r = _result(curriculum, lexicon, renderer, L024_07, HA_AND_FATHA)
    assert any(e.more for e in r.feedback)  # «как сказать» есть — но на экран не идёт
    text = _text(screens.result(curriculum, r, has_audio=True))
    assert "👄" not in text and "Подробнее" not in text
    assert "Нужно:" not in text and "У тебя:" not in text
    _no_marks(text)


def test_result_is_one_message_when_it_fits(
    curriculum: Curriculum, lexicon: Lexicon, renderer: FeedbackRenderer, drawn: list[Any]
) -> None:
    """Разбор короткий — одно сообщение: подпись к картинке, без второго сообщения."""
    for item, heard in ((L024_07, HA_AND_FATHA), (L020_06, THREE_KINDS), (L020_06, SWAP_ALL)):
        s = screens.result(curriculum, _result(curriculum, lexicon, renderer, item, heard), True)
        assert s.details == "", heard
        assert len(s.caption) <= screens.CAPTION_LIMIT


def test_overflowing_result_loses_nothing(
    curriculum: Curriculum, lexicon: Lexicon, renderer: FeedbackRenderer, no_image: None
) -> None:
    """Не влезает в подпись (учитель, длинное «исправлено») — подпись ≤ 1024, а подписи всех
    групп всё равно есть в caption + details."""
    r = _result(curriculum, lexicon, renderer, L020_06, THREE_KINDS, previous=40)
    assert r.breakdown is not None
    r = replace(
        r, fixed=tuple(f"{g.need_label} {i}" for i in range(40) for g in r.breakdown.groups)
    )
    s = screens.result(curriculum, r, has_audio=True, staff=True)
    assert len(s.caption) <= screens.CAPTION_LIMIT
    assert r.breakdown is not None
    for g in r.breakdown.groups:
        assert g.need_label in _text(s) and g.heard_label in _text(s)


def test_result_image_shows_the_review(
    curriculum: Curriculum, lexicon: Lexicon, renderer: FeedbackRenderer, drawn: list[Any]
) -> None:
    """Картинка рисуется по тем же группам, что и текст (номер над буквой = номер пункта)."""
    r = _result(curriculum, lexicon, renderer, L024_07, HA_AND_FATHA)
    s = screens.result(curriculum, r, has_audio=True)
    assert s.image == b"marks.png"
    (call,) = drawn
    assert call.arguments["text"] == r.item.text and call.arguments["breakdown"] is r.breakdown


def test_before_and_after_stays_in_percent_and_fixed_is_by_letter(
    curriculum: Curriculum, lexicon: Lexicon, renderer: FeedbackRenderer, drawn: list[Any]
) -> None:
    """«Было → стало» — в процентах; «✨ Исправлено» — подписями групп, без значков (Р1)."""
    before = _result(curriculum, lexicon, renderer, L024_07, HA_AND_FATHA)
    assert before.breakdown is not None
    fixed = tuple(g.need_label for g in before.breakdown.groups)
    r = replace(
        _result(curriculum, lexicon, renderer, L024_07, HA_AND_FATHA, previous=40), fixed=fixed
    )
    now = r.attempt.assessment.score
    text = _text(screens.result(curriculum, r, has_audio=True))
    assert texts.RESULT_PROGRESS.format(trend=texts.TREND_UP, before=40, now=now) in text
    (line,) = [ln for ln in text.splitlines() if "✨" in ln]
    assert all(label in line for label in fixed)
    _no_marks(text)


# ---------- склонение: «(2 раза)», «Верно 2 слова» ----------
@pytest.mark.parametrize(
    ("n", "word"),
    [(2, "раза"), (5, "раз"), (21, "раз"), (22, "раза"), (11, "раз")],
    ids=["2", "5", "21", "22", "11"],
)
def test_times_is_declined(n: int, word: str) -> None:
    """«(2 раза)», «(5 раз)»: склонение как у дней серии (screens._days)."""
    assert views.plural(n, texts.TIMES_FORMS) == word
    assert views.times(n) == texts.GROUP_TIMES.format(n=n, word=word)
    assert f"{n} {word}" in views.times(n)


def test_one_time_is_not_shown() -> None:
    """Одно место — «(1 раз)» не пишем вовсе."""
    assert views.times(1) == ""


@pytest.mark.parametrize(
    ("n", "word"),
    [(1, "слово"), (2, "слова"), (5, "слов"), (11, "слов"), (21, "слово"), (22, "слова")],
    ids=["1", "2", "5", "11", "21", "22"],
)
def test_words_counter_is_declined(n: int, word: str) -> None:
    assert views.plural(n, texts.WORD_FORMS) == word


# ---------- раунд 2: вид пункта (Р6, Р7), баги ревью 2026-10-24 ----------
L001_03 = "L001-03"  # басмала
BASMALA_PHONEMES = "بِسمِللَااهِررَحمَاانِررَحِۦۦۦۦم"  # quran-transcript, MOSHAF_PARAMS бота
L031_03 = "L031-03"  # بَا بِي بُو تَا تِي تُو ثَا ثِي ثُو
L031_03_PHONEMES = "بَاابِۦۦبُۥۥتَااتِۦۦتُۥۥثَااثِۦۦثُۥۥ"
L040_01 = "L040-01"  # ذُكِّرَ عُلِّمَ كُمِّلَ شُمِّرَ صُنِّفَ صُوِّرَ غُيِّرَ
L040_01_PHONEMES = "ذُككِرَعُللِمَكُممممِلَشُممممِرَصُننننِفَصُووِرَغُييِر"
L043_08 = "L043-08"  # دَلْوٍ شَرْهٌ مَقْتًا نِعْمَةٍ شُكُورًا
L043_08_PHONEMES = "دَلوِنشَرهُنمَقڇتَننِعمَتِنشُكُۥۥرَن"
L086_05 = "L086-05"  # أَحَدٌ
AHAD_PHONEMES = "ءَحَدُن"


def _one_point(c: Curriculum, lexicon: Lexicon, renderer: FeedbackRenderer, *case: str) -> str:
    """Экран с одной группой: её пункт (эталон-фонемы, как в работе)."""
    item, reference, heard = case
    r = _result(c, lexicon, renderer, item, heard, reference)
    assert r.breakdown is not None and len(r.breakdown.groups) == 1, r.breakdown
    return _point(_text(screens.result(c, r, has_audio=True)), 1)


def test_every_point_line_starts_in_russian(
    curriculum: Curriculum, lexicon: Lexicon, renderer: FeedbackRenderer, no_image: None
) -> None:
    """Р6: строка, начатая арабской буквой, в Telegram может развернуться справа налево —
    каждая строка пункта и строка слов начинаются по-русски (после номера)."""
    for item, heard in ((L024_07, HA_AND_FATHA), (L020_06, THREE_KINDS)):
        r = _result(curriculum, lexicon, renderer, item, heard)
        assert r.breakdown is not None
        text = _text(screens.result(curriculum, r, has_audio=True))
        for n in range(1, len(r.breakdown.groups) + 1):
            for line in _point(text, n).splitlines():
                if line.strip():
                    assert _russian_first(line), line


def test_other_letter_is_named_without_lesson_mark(
    curriculum: Curriculum, lexicon: Lexicon, renderer: FeedbackRenderer, no_image: None
) -> None:
    """Р6: «Буква урока» — только у буквы урока; прочие — «Буква ر (Ра): нужно …, у тебя …»."""
    r = _result(curriculum, lexicon, renderer, L020_06, THREE_KINDS)  # урок ص; ر→ل, ب→م
    text = _text(screens.result(curriculum, r, has_audio=True))
    second = _point(text, 2)
    assert f"Буква ر ({lexicon.consonants['ر'][0]})" in second
    assert "Буква урока" not in second and text.count("Буква урока") == 1


def test_kasra_is_a_sign_under_the_letter(
    curriculum: Curriculum, lexicon: Lexicon, renderer: FeedbackRenderer, drawn: list[Any]
) -> None:
    """Р6: кясра — «Знак под س — кясра», фатха и дамма — «над»."""
    point = _one_point(curriculum, lexicon, renderer, L024_07, "", "مُحْسَنُ مَحْشَرُ مِنْحَرُ مَحْفَلُ أَحْسَنَ")
    assert "Знак под س" in point and "кясра" in point and "Знак над" not in point


def test_same_sign_swap_on_many_letters_is_one_point_without_a_letter(
    curriculum: Curriculum, lexicon: Lexicon, renderer: FeedbackRenderer, drawn: list[Any]
) -> None:
    """Р7: «дамма → фатха» на всех буквах L040-01 — один пункт «Знак дамма: нужно «у», у тебя
    «а» (7 раз)» со словами, без буквы-носителя."""
    heard = L040_01_PHONEMES.replace("ُ", "َ")
    point = _one_point(curriculum, lexicon, renderer, L040_01, L040_01_PHONEMES, heard)
    assert "Знак" in point and "дамма" in point
    assert "Знак над" not in point and "Знак под" not in point
    assert views.times(L040_01_PHONEMES.count("ُ")) in point


@pytest.mark.parametrize(
    ("item", "reference", "heard", "says", "never"),
    [
        (L031_03, L031_03_PHONEMES, L031_03_PHONEMES.replace("اا", "ا", 1),
         "тяни дольше", "мадд"),
        (L024_07, L024_07_PHONEMES, "مُحسِنُمَاحشَرُمِنحَرُمَحفَلُءَحسَنَ",
         "коротко, без растяжки", "мадд"),
        (L024_07, L024_07_PHONEMES, "مُحسِنُمَحَرُمِنحَرُمَحفَلُءَحسَنَ",
         "у тебя пропущено", "у тебя —"),
        (L024_07, L024_07_PHONEMES, "مُحسِنُمَحشَرُمِنحَرُمَحفَلُءَحسَنَن",
         "Лишний звук", "у тебя —"),
        (L040_01, L040_01_PHONEMES, L040_01_PHONEMES.replace("كك", "ك", 1),
         "удвой звук", "у тебя —"),
    ],
    ids=["madd_short", "madd_long", "missing", "extra", "shadda"],
)  # fmt: skip
def test_point_says_what_to_do_in_plain_words(  # noqa: PLR0917
    curriculum: Curriculum,
    lexicon: Lexicon,
    renderer: FeedbackRenderer,
    drawn: list[Any],
    item: str,
    reference: str,
    heard: str,
    says: str,
    never: str,
) -> None:
    """Р6: мадд — «тяни дольше» / «коротко, без растяжки» (слово «мадд» новичку не нужно);
    пропуск — «у тебя пропущено», лишнее — «Лишний звук … — в строке его нет», шадда — «удвой
    звук»; «у тебя —» нигде."""
    point = _one_point(curriculum, lexicon, renderer, item, reference, heard)
    assert says in point and never not in point
    if says == "Лишний звук":
        assert "в строке его нет" in point


def test_zero_right_words_counter_is_hidden(
    curriculum: Curriculum, lexicon: Lexicon, renderer: FeedbackRenderer, drawn: list[Any]
) -> None:
    """Р6: «Верно 0 слов из 6» не показываем — ошибки во всех словах."""
    r = _result(curriculum, lexicon, renderer, L020_06, SWAP_ALL)
    assert r.breakdown is not None and r.breakdown.words_ok == 0
    assert "Верно 0" not in _text(screens.result(curriculum, r, has_audio=True))


@pytest.mark.parametrize("stop", [24, 14], ids=["in_last_word", "in_third_word"])
def test_basmala_cut_in_a_word_says_where_the_recording_ended(
    curriculum: Curriculum,
    lexicon: Lexicon,
    renderer: FeedbackRenderer,
    drawn: list[Any],
    stop: int,
) -> None:
    """B1: басмала оборвана посреди слова — есть строка «⏹ …», а «Верно 4 слова из 4» нет."""
    r = _result(curriculum, lexicon, renderer, L001_03, BASMALA_PHONEMES[:stop], BASMALA_PHONEMES)
    text = _text(screens.result(curriculum, r, has_audio=True))
    assert "⏹" in text or texts.ERROR_NUMBERS[0] in text
    assert _words_right(4, 4) not in text


def test_tanwin_and_letters_are_shown_as_written(
    curriculum: Curriculum, lexicon: Lexicon, renderer: FeedbackRenderer, drawn: list[Any]
) -> None:
    """M3: пункт и легенда называют букву как в тексте — ة (не ت), أ (не ء); пропуск «н» танвина
    не называет ن — её нет в слове."""
    cases = [
        (L043_08, L043_08_PHONEMES, L043_08_PHONEMES.replace("نِعمَتِن", "نِعمَدِن"), "ت"),
        (L086_05, AHAD_PHONEMES, "عَحَدُن", "ء"),
        (L043_08, L043_08_PHONEMES, L043_08_PHONEMES.replace("دَلوِن", "دَلوِ", 1), "ن"),
    ]
    for item, reference, heard, absent in cases:
        r = _result(curriculum, lexicon, renderer, item, heard, reference)
        assert r.breakdown is not None and r.breakdown.groups
        point = _point(_text(screens.result(curriculum, r, has_audio=True)), 1)
        assert absent not in point, (item, point)
        legend = " ".join(f"{need} {heard_}" for _, need, heard_ in render.legend_rows(r.breakdown))
        assert absent not in legend, (item, legend)


def test_learner_literals_live_in_texts() -> None:
    """Р6: «Буква урока», «…», «×» ученику — только из texts.py (черновики правит автор), не
    строками в screens.py и render.py."""
    import ast  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    telegram = Path(screens.__file__).parent
    for name in ("screens.py", "render.py"):
        tree = ast.parse((telegram / name).read_text(encoding="utf-8"))
        docstrings = {
            id(node.body[0].value)
            for node in ast.walk(tree)
            if isinstance(node, ast.Module | ast.FunctionDef | ast.ClassDef)
            and node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
        }
        literals = [
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
        ]
        for marker in ("Буква урока", "…", "×"):
            assert not [lit for lit in literals if marker in lit], (name, marker)


# ---------- раунд 3: текст и картинка согласованы (Н1) ----------
BASMALA_WASL = "بِسمِللَااهِررَحمَاانِررَحِۦۦمِ"  # L001-03, quran-transcript (wasl)


def test_groups_sent_to_the_image_are_on_the_image(
    curriculum: Curriculum, lexicon: Lexicon, renderer: FeedbackRenderer, drawn: list[Any]
) -> None:
    """Н1: басмала, ничего не услышано — 10 групп. Выбранное устройство: в тексте — первые
    ``views.MAX_ERRORS_SHOWN``, в легенде картинки — группы 1..``render.LEGEND_MAX_ROWS``;
    «Ещё K — на картинке» называет ровно тех, кто реально есть в легенде после текста, а кого нет
    нигде — отдельной строкой ``texts.MORE_NOT_SHOWN`` с их числом. Каждая группа — в тексте, в
    легенде или в этом явном остатке."""
    r = _result(curriculum, lexicon, renderer, L001_03, "", BASMALA_WASL)
    assert r.breakdown is not None
    total = len(r.breakdown.groups)
    assert total > render.LEGEND_MAX_ROWS
    text = _text(screens.result(curriculum, r, has_audio=True))
    legend = {n for n, *_ in render.legend_rows(r.breakdown)}
    shown = views.MAX_ERRORS_SHOWN
    assert legend == set(range(1, min(total, render.LEGEND_MAX_ROWS) + 1))
    on_image = len(legend - set(range(1, shown + 1)))
    hidden = total - max(len(legend), shown)
    assert texts.MORE_ON_IMAGE.format(n=on_image) in text
    assert texts.MORE_NOT_SHOWN.format(n=hidden) in text
    assert texts.MORE_ON_IMAGE.format(n=total - shown) not in text

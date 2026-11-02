"""FR-61 (ADR-0077): разбор аятов на слоги — файл curriculum/syllables/ayat.yaml и его адаптер.

``SyllableLibrary.load(path)`` (``path`` — сам файл ``ayat.yaml``) повторяет ``VideoLibrary``
(ADR-0074): поиск по точному тексту пункта, ``status: bad`` не отдаётся, ``unchecked`` — отдаётся,
нет файла — пустая библиотека, строка, чьи кусочки не складываются в ``text``, пропускается.
Первая часть — временный yaml, вторая — настоящие данные репозитория (без extra ``ml``, модели и
сети): файл ↔ программа, ``moshaf`` == ``MOSHAF_PARAMS``, якорные проверки правил разбора.

Тексты аятов — из curriculum/course.ru.yaml (через фикстуру ``curriculum``). Порядок огласовок в
программе — «шадда, потом фатха» (не NFC), поэтому якорные кусочки сравниваются после NFC, а
склейка кусочков с ``text`` — точно.
"""

import re
import unicodedata
from pathlib import Path
from typing import Any

import pytest
import yaml

from muallim.domain.curriculum import Curriculum
from muallim.infrastructure.asr.muaalem import MOSHAF_PARAMS  # без torch и quran_transcript

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
AYAT = ROOT / "curriculum" / "syllables" / "ayat.yaml"
STATUSES = {"unchecked", "ok", "bad"}

BASMALA = "L097-02"  # بِسْمِ ٱللَّهِ ٱلرَّحْمَـٰنِ ٱلرَّحِيمِ — 1:1
AR_RAHMAN = "L097-04"  # ٱلرَّحْمَـٰنِ ٱلرَّحِيمِ — 1:3
ALIF_LAM_MIM = "L098-02"  # الٓمٓ — 2:1
DHALIKA = "L098-03"  # 2:2


def _whole_words(text: str, sound: str = "звук") -> list[list[list[str]]]:
    """Каждое слово — одна клетка: кусочки точно складываются в ``text``."""
    return [[[word, sound]] for word in text.split(" ")]


def _write(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"moshaf": dict(MOSHAF_PARAMS), "ayat": rows}
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def _load(path: Path) -> Any:
    from muallim.infrastructure.curriculum.syllables import SyllableLibrary  # noqa: PLC0415

    return SyllableLibrary.load(path)


@pytest.fixture
def texts(curriculum: Curriculum) -> dict[str, str]:
    return {i: curriculum.item(i).text for i in (BASMALA, AR_RAHMAN, ALIF_LAM_MIM, DHALIKA)}


@pytest.fixture
def library(tmp_path: Path, texts: dict[str, str]) -> Any:
    alm = texts[ALIF_LAM_MIM]
    rows = [
        {"text": texts[BASMALA], "status": "ok", "words": _whole_words(texts[BASMALA])},
        {"text": texts[AR_RAHMAN], "status": "unchecked", "words": _whole_words(texts[AR_RAHMAN])},
        {"text": texts[DHALIKA], "status": "bad", "words": _whole_words(texts[DHALIKA])},
        # кусочки не складываются в текст: не хватает «مٓ»
        {"text": alm, "status": "ok", "words": [[[alm[:-2], "алиф-лаам"]]]},
    ]
    return _load(_write(tmp_path / "syllables" / "ayat.yaml", rows))


# ---------- адаптер на временном файле ----------
def test_checked_row_is_given_as_words_of_cells(library: Any, texts: dict[str, str]) -> None:
    from muallim.domain.syllables import SyllableCell  # noqa: PLC0415

    words = library.for_text(texts[BASMALA])
    assert words is not None
    assert isinstance(words, tuple) and all(isinstance(w, tuple) for w in words)
    assert words == tuple((SyllableCell(w, "звук"),) for w in texts[BASMALA].split(" "))


def test_unchecked_row_is_given_like_unchecked_video(library: Any, texts: dict[str, str]) -> None:
    from muallim.domain.syllables import SyllableCell  # noqa: PLC0415

    first, second = texts[AR_RAHMAN].split(" ")
    assert library.for_text(texts[AR_RAHMAN]) == (
        (SyllableCell(first, "звук"),),
        (SyllableCell(second, "звук"),),
    )


def test_rejected_row_is_not_given(library: Any, texts: dict[str, str]) -> None:
    assert library.for_text(texts[DHALIKA]) is None


def test_row_whose_pieces_do_not_add_up_to_text_is_skipped(
    library: Any, texts: dict[str, str]
) -> None:
    assert library.for_text(texts[ALIF_LAM_MIM]) is None


def test_unknown_text_gives_nothing(library: Any, curriculum: Curriculum) -> None:
    assert library.for_text(curriculum.item("L097-03").text) is None  # 1:2 — не в файле
    assert library.for_text("") is None


def test_missing_file_is_an_empty_library(tmp_path: Path, texts: dict[str, str]) -> None:
    empty = _load(tmp_path / "нет" / "ayat.yaml")
    assert empty.for_text(texts[BASMALA]) is None


def test_syllable_library_implements_the_port(tmp_path: Path, texts: dict[str, str]) -> None:
    from muallim.infrastructure.curriculum.syllables import SyllableLibrary  # noqa: PLC0415

    path = _write(tmp_path / "ayat.yaml", [_ok(texts[BASMALA], _whole_words(texts[BASMALA]))])
    from muallim.application.ports.reading import AyahSyllables  # noqa: PLC0415

    port: AyahSyllables = SyllableLibrary.load(path)  # mypy --strict сверяет класс с портом
    assert port.for_text(texts[BASMALA]) is not None
    assert port.for_text("нет") is None


def _ok(text: str, words: list[list[list[str]]]) -> dict[str, Any]:
    return {"text": text, "status": "ok", "words": words}


def _broken(kind: str, text: str) -> list[list[list[str]]]:
    words = _whole_words(text)
    if kind == "extra_piece":  # лишний кусок в последнем слове
        words[-1].append([words[-1][0][0][-2:], "лишний"])
    elif kind == "fewer_words":  # два первых слова склеены в одно
        words = [[words[0][0], words[1][0]], *words[2:]]
    elif kind == "nfc_only":  # те же буквы, но огласовки в порядке NFC
        words = [[[unicodedata.normalize("NFC", w[0][0]), "звук"]] for w in words]
    return words


@pytest.mark.parametrize("kind", ["extra_piece", "fewer_words", "nfc_only"])
def test_row_that_adds_up_only_approximately_is_skipped(
    tmp_path: Path, curriculum: Curriculum, kind: str
) -> None:
    """Склейка точная: ни лишнего куска, ни другого числа слов, ни «равно после NFC»."""
    text = curriculum.item("L097-08").text  # 1:7 — шадда перед фатхой, не NFC
    assert unicodedata.normalize("NFC", text) != text
    broken = _broken(kind, text)
    joined = " ".join("".join(c[0] for c in w) for w in broken)
    if kind == "fewer_words":
        assert joined.replace(" ", "") == text.replace(" ", "") and joined != text
    elif kind == "nfc_only":
        assert unicodedata.normalize("NFC", joined) == unicodedata.normalize("NFC", text)
    library = _load(_write(tmp_path / "ayat.yaml", [_ok(text, broken)]))
    assert library.for_text(text) is None


# ---------- настоящие данные: curriculum/syllables/ayat.yaml ----------
def _data() -> dict[str, Any]:
    assert AYAT.is_file(), "нет curriculum/syllables/ayat.yaml — make syllables"
    data = yaml.safe_load(AYAT.read_text(encoding="utf-8"))
    assert isinstance(data, dict) and isinstance(data.get("ayat"), list)
    return data


def _rows() -> list[dict[str, Any]]:
    return list(_data()["ayat"])


def _sura_texts(curriculum: Curriculum) -> set[str]:
    return {
        i.text for les in curriculum.lessons if les.section == "sura" for i in les.items if i.quran
    }


def _row(text: str) -> dict[str, Any]:
    [row] = [r for r in _rows() if r["text"] == text]
    return row


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def test_ayat_file_exists() -> None:
    assert AYAT.is_file()


def test_every_sura_ayah_of_the_program_is_in_the_file(curriculum: Curriculum) -> None:
    """Новая сура или изменённый аят → красный тест, пока файл не пересобран (make syllables)."""
    have = {r["text"] for r in _rows()}
    missing = sorted(_sura_texts(curriculum) - have)
    assert not missing, missing


def test_every_file_row_is_a_sura_ayah_of_the_program(curriculum: Curriculum) -> None:
    """Нет лишних и устаревших строк."""
    extra = [r["text"] for r in _rows() if r["text"] not in _sura_texts(curriculum)]
    assert not extra, extra


def test_each_text_has_exactly_one_row() -> None:
    texts = [r["text"] for r in _rows()]
    assert len(texts) == len(set(texts))  # басмала — одна строка на 29 сур


def test_pieces_add_up_exactly_to_the_ayah_text() -> None:
    bad = []
    for row in _rows():
        words = row["words"]
        if len(words) != len(row["text"].split()):
            bad.append(row["text"])
            continue
        if " ".join("".join(cell[0] for cell in word) for word in words) != row["text"]:
            bad.append(row["text"])
    assert not bad, bad


def test_every_cell_has_a_piece_and_a_caption() -> None:
    empty = [
        (row["text"], cell)
        for row in _rows()
        for word in row["words"]
        for cell in word
        if len(cell) != 2 or not str(cell[0]).strip() or not str(cell[1]).strip()
    ]
    assert not empty, empty


def test_status_is_unchecked_ok_or_bad() -> None:
    assert {r["status"] for r in _rows()} <= STATUSES


def test_file_was_built_with_the_bot_moshaf_params() -> None:
    """Изменили ``MOSHAF_PARAMS`` — файл устарел (ADR-0077, «Последствия»)."""
    assert _data()["moshaf"] == MOSHAF_PARAMS


def test_repository_file_is_read_by_the_library_for_every_good_row() -> None:
    library = _load(AYAT)
    for row in _rows():
        found = library.for_text(row["text"])
        assert (found is None) == (row["status"] == "bad"), row["text"]


# ---------- якорные проверки правил разбора (регрессия генератора) ----------
def _cells(row: dict[str, Any]) -> list[list[tuple[str, str]]]:
    return [[(_nfc(c[0]), c[1]) for c in word] for word in row["words"]]


def test_basmala_is_split_as_approved(curriculum: Curriculum) -> None:
    expected = [
        [("بِسْ", "бис"), ("مِ", "ми")],
        [("ٱللَّ", "ллаа"), ("هِ", "хи")],
        [("ٱلرَّحْ", "ррах"), ("مَـٰ", "маа"), ("نِ", "ни")],
        [("ٱلرَّ", "рра"), ("حِيمِ", "хиим")],
    ]
    got = _cells(_row(curriculum.item(BASMALA).text))
    assert got == [[(_nfc(t), s) for t, s in word] for word in expected]


def test_ayah_start_keeps_wasl_alif_and_silent_lam_with_first_sound(
    curriculum: Curriculum,
) -> None:
    """1:3 с начала аята: ٱ + немая ل — в одной клетке с первой звучащей, «аррах»."""
    first = _cells(_row(curriculum.item(AR_RAHMAN).text))[0][0]
    assert first == (_nfc("ٱلرَّحْ"), "аррах")


def test_disjoined_letters_are_one_cell(curriculum: Curriculum) -> None:
    """2:1 الٓمٓ — хуруф мукатта'а: одна клетка."""
    text = curriculum.item(ALIF_LAM_MIM).text
    assert _row(text)["words"] == [[[text, "а-лиф-лаам-миим"]]]


def test_no_caption_repeats_a_letter_three_times() -> None:
    """Гунна, мадд лин, идгам танвина — повторы сжаты: «ммм», «ааа» не бывает."""
    triple = re.compile(r"(.)\1\1", re.IGNORECASE)
    bad = [
        (row["text"], cell[1])
        for row in _rows()
        for word in row["words"]
        for cell in word
        if triple.search(str(cell[1]))
    ]
    assert not bad, bad


# Соединение букв как в мусхафе (ревью FR-61, 2026-10-31)
_ALIF_FORMS = frozenset("اأإآٱ")


def _last_letter(piece: str) -> str:
    """Последняя буква кусочка без огласовок и знаков (ۥ ۦ — знаки, не буквы)."""
    import unicodedata  # noqa: PLC0415

    letters = [ch for ch in piece if unicodedata.category(ch) == "Lo" and ch not in "ۥۦ"]
    return letters[-1] if letters else ""


def _first_letter(piece: str) -> str:
    """Первый знак кусочка: татвиль «ـ» перед алифом — не лигатура «لا» и в самом мусхафе."""
    return piece[:1]


def test_lam_alif_ligature_is_never_split_between_cells() -> None:
    """«لا» в мусхафе — одна лигатура: ل и следующий за ним алиф в одной клетке (ٱلْأَكْ, не ٱلْ|أَكْ)."""
    split = [
        (row["text"], word[k][0], word[k + 1][0])
        for row in _rows()
        for word in row["words"]
        for k in range(len(word) - 1)
        if _last_letter(word[k][0]) == "ل" and _first_letter(word[k + 1][0]) in _ALIF_FORMS
    ]
    assert not split, split


def test_broken_rows_are_skipped_and_bot_still_starts(
    tmp_path: Path, texts: dict[str, str]
) -> None:
    """Человек правит status руками: строка-не-словарь или без text не роняет загрузку."""
    good = _ok(texts[BASMALA], _whole_words(texts[BASMALA]))
    broken: list[Any] = ["oops", {"status": "ok"}, {"text": 5}]
    path = _write(tmp_path / "ayat.yaml", [*broken, good])
    library = _load(path)
    assert library.for_text(texts[BASMALA]) is not None


def test_unreadable_yaml_is_an_empty_library(tmp_path: Path, texts: dict[str, str]) -> None:
    path = tmp_path / "ayat.yaml"
    path.write_text("ayat: [\n  - text: :::\n", encoding="utf-8")
    assert _load(path).for_text(texts[BASMALA]) is None

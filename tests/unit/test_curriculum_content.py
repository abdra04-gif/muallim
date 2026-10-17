"""Программа = вся книга в её порядке (ADR-0022, ADR-0025). Арабский текст сверяет человек."""

from pathlib import Path

import yaml

from muallim.domain.curriculum import Curriculum, ItemKind, Lesson
from muallim.domain.phonetics import CONSONANTS

ROOT = Path(__file__).resolve().parents[2]
BOOK = "SRC-040"
# Порядок букв в разделе «Арабский алфавит», с. 10–24 (book/README.md)
BOOK_LETTER_ORDER = "ءرزمتنيبكلوهفقشسثصطجخحغعدضذظ"
FATHA, KASRA, DAMMA = "َ", "ِ", "ُ"
BOOK_SECTIONS = [  # разделы книги по оглавлению (book/contents.yaml), в её порядке
    "start", "alphabet", "letter", "madd", "exercises", "tashdid", "tanwin", "tanwin_tashdid",
    "hamza", "wasla", "ta_marbuta", "sukun", "article", "mim", "noon_izhar", "noon_idgham",
    "noon_ikhfa", "iqlab", "qalqala", "small", "ya_alif", "waw_alif", "silent", "noon_kasra",
    "waqf", "sakt", "madd_types", "muqattaat", "signs", "sura",
]  # fmt: skip
SURA_ORDER = [1, 2, 93, 94, 95, 96, 97, 98, 99, 100, 101, 102, 103, 104, 105, 106, 107, 108, 109,
              110, 111, 112, 113, 114]  # fmt: skip


def _lessons(c: Curriculum, section: str) -> list[Lesson]:
    return [lesson for lesson in c.lessons if lesson.section == section]


def test_sections_follow_book_contents(curriculum: Curriculum) -> None:
    seen: list[str] = []
    for lesson in curriculum.lessons:
        if not seen or seen[-1] != lesson.section:
            seen.append(lesson.section)
    assert seen == BOOK_SECTIONS


def test_starts_with_istiadha_and_basmala(curriculum: Curriculum) -> None:
    first = curriculum.lessons[0]
    texts = [i.text for i in first.items if i.is_practice]
    assert texts[0].startswith("أَعُوذُ") and texts[1].startswith("بِسْمِ")
    assert first.items[1].source is not None and first.items[1].source.page == 10


def test_alphabet_table_from_page_10(curriculum: Curriculum) -> None:
    (lesson,) = _lessons(curriculum, "alphabet")
    rows = [i.text.split() for i in lesson.items if i.kind is ItemKind.ALPHABET]
    assert [len(r) for r in rows] == [7, 8, 7, 7]
    assert {c for row in rows for c in row} == CONSONANTS | {"ا"}


def test_letter_lessons_follow_book_letter_order(curriculum: Curriculum) -> None:
    heads = [
        next(i for i in les.items if i.kind is ItemKind.LETTER)
        for les in _lessons(curriculum, "letter")
    ]
    letters = "".join("ء" if h.text[0] == "أ" else h.text[0] for h in heads)
    assert letters == BOOK_LETTER_ORDER
    for head in heads:
        assert [s[-1] for s in head.text.split()] == [FATHA, KASRA, DAMMA], head.id
        assert head.name and head.sound and head.tip, head.id


def test_suras_are_the_books_suras_in_order(curriculum: Curriculum) -> None:
    suras: list[int] = []
    for lesson in _lessons(curriculum, "sura"):
        for item in lesson.items:
            sura = int(item.quran.split(":")[0]) if item.quran and item.quran != "1:1" else None
            if sura and (not suras or suras[-1] != sura):
                suras.append(sura)
    assert suras == SURA_ORDER  # 1:1 — басмала: она и перед каждой сурой, поэтому не считается
    fatiha = {i.quran for les in _lessons(curriculum, "sura") for i in les.items}
    assert {f"1:{a}" for a in range(1, 8)} <= fatiha


def test_every_section_explains_its_rule(curriculum: Curriculum) -> None:
    sections = {les.section for les in curriculum.lessons}
    explained = {
        les.section for les in curriculum.lessons for i in les.items if i.kind is ItemKind.RULE
    }
    assert sections <= explained
    for les in curriculum.lessons:
        for item in les.items:
            if item.kind is ItemKind.RULE:
                assert item.name and len(item.tip) > 60 and not item.is_practice, item.id


def test_every_item_points_to_book_page(curriculum: Curriculum) -> None:
    pages = []
    for lesson in curriculum.lessons:
        for item in lesson.items:
            src = item.source
            assert src is not None and src.source_id == BOOK, item.id
            assert src.page is not None and 10 <= src.page <= 85, item.id
            assert src.line is not None and src.line >= 1, item.id
            pages.append(src.page)
    assert pages == sorted(pages), "карточки идут в порядке страниц книги"


def test_quran_items_have_valid_reference(curriculum: Curriculum) -> None:
    refs = [i.quran for les in curriculum.lessons for i in les.items if i.quran]
    assert len(refs) > 300
    for ref in refs:
        sura, aya = (int(x) for x in ref.split(":"))
        assert 1 <= sura <= 114 and aya >= 1, ref


def test_lessons_are_short_and_ids_sequential(curriculum: Curriculum) -> None:
    for n, lesson in enumerate(curriculum.lessons, start=1):
        assert (lesson.number, lesson.id) == (n, f"L{n:03}")
        assert len(lesson.practice_items) <= 12, lesson.id
        assert lesson.part, lesson.id
        for item in lesson.items:
            assert item.id.startswith(lesson.id + "-"), item.id


def test_parts_group_lessons_in_order(curriculum: Curriculum) -> None:
    parts = curriculum.parts()
    assert [name.split(".")[0] for name, _ in parts] == [str(i) for i in range(1, 10)]
    assert [les for _, lessons in parts for les in lessons] == list(curriculum.lessons)


def test_book_lines_have_no_invented_translation(curriculum: Curriculum) -> None:
    for lesson in curriculum.lessons:
        for item in lesson.items:
            if item.kind is ItemKind.LINE:
                assert item.text and not item.translation and not item.sound, item.id


def test_lexicon_knows_every_consonant(curriculum: Curriculum) -> None:
    assert set(curriculum.lexicon.consonants) == CONSONANTS
    assert set(curriculum.lexicon.letter_tips) == CONSONANTS


def test_pair_tips_only_reference_known_letters(curriculum: Curriculum) -> None:
    for pair in curriculum.lexicon.pair_tips:
        assert len(pair) == 2 and pair <= CONSONANTS, pair


def test_book_contents_map_points_to_existing_lessons(curriculum: Curriculum) -> None:
    contents = yaml.safe_load((ROOT / "book" / "contents.yaml").read_text(encoding="utf-8"))
    mapped = [lid for section in contents["sections"] for lid in section["lessons"]]
    assert mapped == [lesson.id for lesson in curriculum.lessons]


def test_only_russian_language_files_are_active() -> None:
    active = sorted(p.name for p in (ROOT / "curriculum").glob("*.yaml"))
    assert active == ["course.ru.yaml", "feedback.ru.yaml", "lexicon.ru.yaml"]


def test_each_vowel_is_practised_alone_before_the_book_row(curriculum: Curriculum) -> None:
    """ADR-0032: «как произносить» → ـَ, ـِ, ـُ по одной карточке → строка книги целиком."""
    for les in _lessons(curriculum, "letter"):
        kinds = [i.kind for i in les.items]
        head = kinds.index(ItemKind.LETTER)
        syllables = [i for i in les.items[:head] if i.kind is ItemKind.SYLLABLE]
        assert kinds[0] is ItemKind.RULE, les.id
        assert [s.text for s in syllables] == les.items[head].text.split(), les.id
        assert [s.sound for s in syllables] == les.items[head].sound.split(" · "), les.id
        for s in syllables:
            assert s.is_practice and s.name and len(s.tip) > 20, s.id
    assert all(i.kind is not ItemKind.SYLLABLE for les in curriculum.lessons
               if les.section != "letter" for i in les.items)  # fmt: skip


def test_hamza_lesson_explains_each_vowel_right_before_it(curriculum: Curriculum) -> None:
    hamza = _lessons(curriculum, "letter")[0]
    for k, item in enumerate(hamza.items):
        if item.kind is ItemKind.SYLLABLE:
            rule = hamza.items[k - 1]
            assert rule.kind is ItemKind.RULE and rule.text == item.text, item.id
    vowels = [i.text[-1] for i in hamza.items if i.kind is ItemKind.SYLLABLE]
    assert vowels == [FATHA, KASRA, DAMMA]


def test_every_other_letter_lesson_explains_how_to_pronounce(curriculum: Curriculum) -> None:
    for les in _lessons(curriculum, "letter")[1:]:
        rule = les.items[0]
        assert rule.text == les.items[1].text[0] and "Как произносить" in rule.name, les.id
        assert len(rule.tip) > 80, les.id

"""«Как читается» от фонетизатора quran-transcript (FR-43): без модели, только правила чтения."""

import importlib.util
from collections.abc import Iterator
from dataclasses import fields

import pytest

from muallim.domain.curriculum import Curriculum, LessonItem
from muallim.infrastructure.asr.reading import QuranReadingGuide

pytestmark = pytest.mark.integration
needs_phonetizer = pytest.mark.skipif(
    importlib.util.find_spec("quran_transcript") is None, reason="нет extra ml"
)


def _practice(curriculum: Curriculum) -> Iterator[LessonItem]:
    return (i for les in curriculum.lessons for i in les.items if i.is_practice)


@needs_phonetizer
def test_phonemes_of_a_book_syllable() -> None:
    phonemes = QuranReadingGuide().phonemes("بَ")
    assert phonemes is not None and phonemes.startswith("بَ")


@needs_phonetizer
def test_every_card_of_the_book_gets_a_reference(curriculum: Curriculum) -> None:
    """Аудит 2026-10-23: на 36 карточках фонетизатор падал — голосовое не проверялось вовсе."""
    from muallim.infrastructure.asr.muaalem import _references  # noqa: PLC0415

    broken = []
    for item in _practice(curriculum):
        try:
            _references(item.text)
        except Exception as error:  # noqa: BLE001 — собираем все, а не первую
            broken.append(f"{item.id} {item.text}: {error!r}")
    assert not broken, "\n".join(broken)


@needs_phonetizer
def test_reference_contains_only_sounds_the_model_can_hear(curriculum: Curriculum) -> None:
    """Знаки «ٓ» и «آ» — письмо, а не звук: модель их не выдаёт, и в «Как читается» они лишние."""
    from quran_transcript import alphabet  # noqa: PLC0415

    from muallim.infrastructure.asr.muaalem import _references  # noqa: PLC0415

    sounds = {getattr(alphabet.phonetics, f.name) for f in fields(alphabet.phonetics)}
    foreign = []
    for item in _practice(curriculum):
        for name, ref in _references(item.text)[1]:
            extra = {ch for ch in ref if ch not in sounds}
            if extra:
                foreign.append(f"{item.id} {name}: {sorted(extra)}")
    assert not foreign, "\n".join(foreign)


@needs_phonetizer
@pytest.mark.parametrize(
    ("item_id", "doubled"),
    [("L038-02", "بب"), ("L039-01", "ثث"), ("L053-07", "سس"), ("L044-02", "بب")],
)
def test_shadda_on_a_card_doubles_the_consonant(
    curriculum: Curriculum, item_id: str, doubled: str
) -> None:
    """Огласовка перед шаддой (порядок NFC) давала «рабара» вместо «рабба»."""
    from muallim.infrastructure.asr.muaalem import _references  # noqa: PLC0415

    for _, ref in _references(curriculum.item(item_id).text)[1]:
        assert doubled in ref


@needs_phonetizer
def test_unreadable_text_gives_none_instead_of_error() -> None:
    assert QuranReadingGuide().phonemes("ا") is None  # фонетизатор не начинает с алифа


def test_without_phonetizer_package_gives_none(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins  # noqa: PLC0415

    real = builtins.__import__

    def no_phonetizer(name: str, *args: object, **kwargs: object) -> object:
        if name.startswith("quran_transcript"):
            raise ImportError(name)
        return real(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(builtins, "__import__", no_phonetizer)
    assert QuranReadingGuide().phonemes("بَتَ") is None

"""«Как читается» от фонетизатора quran-transcript (FR-43): без модели, только правила чтения."""

import importlib.util

import pytest

from muallim.infrastructure.asr.reading import QuranReadingGuide

pytestmark = pytest.mark.integration
needs_phonetizer = pytest.mark.skipif(
    importlib.util.find_spec("quran_transcript") is None, reason="нет extra ml"
)


@needs_phonetizer
def test_phonemes_of_a_book_syllable() -> None:
    phonemes = QuranReadingGuide().phonemes("بَ")
    assert phonemes is not None and phonemes.startswith("بَ")


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

"""Объяснения на разных языках (FR-22, ADR-0017). Пока включён только русский (ADR-0022)."""

import shutil
from pathlib import Path

import pytest

from muallim.application.feedback import FeedbackCatalog
from muallim.domain.assessment import ErrorKind, assess
from muallim.domain.learner import Learner
from muallim.infrastructure.curriculum.yaml_loader import load_feedback_catalog
from tests.conftest import CURRICULUM_DIR
from tests.fakes import FixedClock, SequentialIds


@pytest.fixture(scope="module")
def drafts(tmp_path_factory: pytest.TempPathFactory) -> FeedbackCatalog:
    """Русский + черновики из curriculum/drafts/: черновики должны оставаться рабочими."""
    work: Path = tmp_path_factory.mktemp("languages")
    for path in [*CURRICULUM_DIR.glob("*.ru.yaml"), *(CURRICULUM_DIR / "drafts").glob("*.yaml")]:
        shutil.copy(path, work / path.name)
    return load_feedback_catalog(work)


def _learner(language: str, feedback_language: str | None = None) -> Learner:
    return Learner(
        SequentialIds().new_id(), 1, "L-1", language, FixedClock().now(),
        feedback_language=feedback_language,
    )  # fmt: skip


def test_russian_is_enabled_and_default(catalog: FeedbackCatalog) -> None:
    assert "ru" in catalog.enabled()
    assert catalog.default == "ru"


def test_bot_loads_only_russian(catalog: FeedbackCatalog) -> None:
    assert catalog.all_languages() == ["ru"]


def test_drafts_are_kept_valid_but_disabled(drafts: FeedbackCatalog) -> None:
    assert {"kk", "en"} <= set(drafts.all_languages())
    assert drafts.enabled() == ["ru"]


def test_every_language_has_template_for_every_error_kind(drafts: FeedbackCatalog) -> None:
    for code in drafts.all_languages():
        templates = drafts.language(code).templates
        assert set(templates.messages) == set(ErrorKind), code


def test_every_language_renders_every_error_kind(drafts: FeedbackCatalog) -> None:
    cases = [("صَ", "سَ"), ("بَ", "بِ"), ("بَ", "بx"), ("بَتَ", "سِ"), ("بَا", "بَ"), ("بَ", "ب"),
             ("رَببَ", "رَبَ"), ("كَتَبَ", "كَتَ"), ("بَ", "بَا"), ("بَ", "بَس")]  # fmt: skip
    for code in drafts.all_languages():
        renderer = drafts.renderer(code)
        for reference, heard in cases:
            assert all(m.strip() for m in renderer.render(assess(reference, heard).errors)), code


def test_resolve_prefers_explicit_choice(catalog: FeedbackCatalog) -> None:
    assert catalog.resolve(_learner("en", feedback_language="ru")) == "ru"


def test_resolve_falls_back_to_default_for_disabled_language(drafts: FeedbackCatalog) -> None:
    assert drafts.resolve(_learner("kk")) == "ru"
    assert drafts.resolve(_learner("kk", feedback_language="kk")) == "ru"


def test_unknown_language_rejected(catalog: FeedbackCatalog) -> None:
    with pytest.raises(KeyError):
        catalog.renderer("zz")

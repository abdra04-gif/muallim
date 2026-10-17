"""Общие фикстуры. Модель распознавания в тестах не грузится никогда (ADR-0006)."""

from pathlib import Path

import pytest

from muallim.application.feedback import FeedbackCatalog, FeedbackRenderer
from muallim.domain.curriculum import Curriculum
from muallim.infrastructure.curriculum.yaml_loader import load_curriculum, load_feedback_catalog

ROOT = Path(__file__).resolve().parents[1]
CURRICULUM_DIR = ROOT / "curriculum"


@pytest.fixture(scope="session")
def curriculum() -> Curriculum:
    return load_curriculum(CURRICULUM_DIR / "course.ru.yaml", CURRICULUM_DIR / "lexicon.ru.yaml")


@pytest.fixture(scope="session")
def catalog() -> FeedbackCatalog:
    return load_feedback_catalog(CURRICULUM_DIR)


@pytest.fixture(scope="session")
def renderer(catalog: FeedbackCatalog) -> FeedbackRenderer:
    return catalog.renderer("ru")

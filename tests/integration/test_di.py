"""Контейнер собирается, и сценарии разрешаются со всеми зависимостями (без модели и Telegram)."""

from pathlib import Path

import pytest
import yaml
from pydantic import SecretStr

from muallim.application.use_cases.annotation import NextAnnotation, RedeemInvite, SubmitAnnotation
from muallim.application.use_cases.cards import OpenItem
from muallim.application.use_cases.curriculum import PublishCurriculum
from muallim.application.use_cases.learners import DeleteMyData, EnsureLearner, SetResearchConsent
from muallim.application.use_cases.progress import GetProgress
from muallim.application.use_cases.quiz import PracticeQuiz
from muallim.application.use_cases.recitation import AssessRecitation
from muallim.bootstrap.config import PROJECT_ROOT, Settings
from muallim.bootstrap.di import create_container
from muallim.infrastructure.db.engine import create_engine
from muallim.infrastructure.db.tables import metadata


async def test_container_resolves_every_use_case(tmp_path: Path) -> None:
    from muallim.application.use_cases.review import GetReview  # noqa: PLC0415

    url = f"sqlite+aiosqlite:///{tmp_path / 'di.sqlite3'}"
    engine = create_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
    await engine.dispose()

    settings = Settings(
        bot_token=SecretStr("0:test"),
        database_url=SecretStr(url),
        asr_backend="stub",
        audio_dir=tmp_path / "audio",
    )
    container = create_container(settings)
    try:
        async with container() as request:
            for uc in (
                EnsureLearner, SetResearchConsent, DeleteMyData, OpenItem, GetProgress,
                AssessRecitation, PublishCurriculum, PracticeQuiz, NextAnnotation, RedeemInvite,
                SubmitAnnotation, GetReview,
            ):  # fmt: skip
                assert isinstance(await request.get(uc), uc)
            published = await (await request.get(PublishCurriculum)).execute()
            assert published > 100  # снимок программы при старте бота (ADR-0023)
            learner, created = await (await request.get(EnsureLearner)).execute(1, "ru")
            result = await (await request.get(AssessRecitation)).execute(learner, b"ogg")
            assert created and result.attempt.assessment.score == 100
    finally:
        await container.close()


async def test_container_resolves_articulation_video(tmp_path: Path) -> None:
    """FR-56 (ADR-0074): сценарии ролика зарегистрированы, библиотека — curriculum/video/."""
    from muallim.application.ports.storage import ArticulationVideoLibrary  # noqa: PLC0415
    from muallim.application.use_cases.video import (  # noqa: PLC0415
        GetArticulationVideo,
        RecordVideoPlayed,
    )

    url = f"sqlite+aiosqlite:///{tmp_path / 'di.sqlite3'}"
    settings = Settings(
        bot_token=SecretStr("0:test"),
        database_url=SecretStr(url),
        asr_backend="stub",
        audio_dir=tmp_path / "audio",
    )
    container = create_container(settings)
    try:
        library = await container.get(ArticulationVideoLibrary)
        assert library.for_letter("ر") is not None  # ролики أ ر ز лежат в репозитории
        async with container() as request:
            for uc in (GetArticulationVideo, RecordVideoPlayed):
                assert isinstance(await request.get(uc), uc)
    finally:
        await container.close()


async def test_container_resolves_ayah_syllables(tmp_path: Path) -> None:
    """FR-61 (ADR-0077): разбор аятов на слоги зарегистрирован, файл — curriculum/syllables/."""
    from muallim.application.ports.reading import AyahSyllables  # noqa: PLC0415
    from muallim.domain.curriculum import Curriculum  # noqa: PLC0415

    url = f"sqlite+aiosqlite:///{tmp_path / 'di.sqlite3'}"
    settings = Settings(
        bot_token=SecretStr("0:test"),
        database_url=SecretStr(url),
        asr_backend="stub",
        audio_dir=tmp_path / "audio",
    )
    container = create_container(settings)
    try:
        library = await container.get(AyahSyllables)
        curriculum = await container.get(Curriculum)
        path = PROJECT_ROOT / "curriculum" / "syllables" / "ayat.yaml"
        rows = yaml.safe_load(path.read_text(encoding="utf-8"))["ayat"]
        good = [r["text"] for r in rows if r["status"] != "bad"]  # статус ставит человек
        if not good:
            pytest.skip("все строки ayat.yaml помечены bad")
        assert library.for_text(good[0]) is not None
        assert library.for_text(curriculum.item("L001-02").text) is None  # не сура
    finally:
        await container.close()

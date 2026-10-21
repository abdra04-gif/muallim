"""Контейнер собирается, и сценарии разрешаются со всеми зависимостями (без модели и Telegram)."""

from pathlib import Path

from pydantic import SecretStr

from muallim.application.use_cases.annotation import NextAnnotation, RedeemInvite, SubmitAnnotation
from muallim.application.use_cases.cards import OpenItem
from muallim.application.use_cases.curriculum import PublishCurriculum
from muallim.application.use_cases.learners import DeleteMyData, EnsureLearner, SetResearchConsent
from muallim.application.use_cases.progress import GetProgress
from muallim.application.use_cases.quiz import PracticeQuiz
from muallim.application.use_cases.recitation import AssessRecitation
from muallim.bootstrap.config import Settings
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

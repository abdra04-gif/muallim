"""Слушатель карточек в контейнере (FR-70; ADR-0088 п. 1, 5, 8): MostafaMaroof по умолчанию,
Muaalem при этом не грузится вообще (решение автора: вся книга и суры — MostafaMaroof);
``checker=muaalem`` — откат на прежнюю модель; заглушка ``make run-stub`` засчитывает.
Модели не грузятся: ``load`` подменён."""

from pathlib import Path

import pytest
from pydantic import SecretStr

from muallim.application.ports.recognition import CardListener
from muallim.application.use_cases.recitation import AssessRecitation
from muallim.bootstrap.config import Settings
from muallim.bootstrap.di import create_container
from muallim.infrastructure.db.engine import create_engine
from muallim.infrastructure.db.tables import metadata

pytestmark = pytest.mark.integration


async def _settings(tmp_path: Path, **kwargs: str) -> Settings:
    url = f"sqlite+aiosqlite:///{tmp_path / 'di.sqlite3'}"
    engine = create_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
    await engine.dispose()
    return Settings(
        bot_token=SecretStr("0:test"),
        database_url=SecretStr(url),
        audio_dir=tmp_path / "audio",
        **kwargs,  # type: ignore[arg-type]
    )


@pytest.fixture
def loaded(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Какие модели загрузились при сборке (вместо настоящей загрузки — отметка)."""
    from muallim.infrastructure.asr.maroof import MaroofListener  # noqa: PLC0415

    from muallim.infrastructure.asr.muaalem import MuaalemRecognizer  # noqa: PLC0415

    calls: list[str] = []
    monkeypatch.setattr(MaroofListener, "load", lambda self: calls.append("maroof"))
    monkeypatch.setattr(MuaalemRecognizer, "load", lambda self: calls.append("muaalem"))
    return calls


def test_checker_is_maroof_by_default() -> None:
    assert Settings(bot_token=SecretStr("0:test")).checker == "maroof"


async def test_maroof_is_the_card_listener_and_muaalem_is_not_loaded(
    tmp_path: Path, loaded: list[str]
) -> None:
    from muallim.infrastructure.asr.maroof import MaroofListener  # noqa: PLC0415

    from muallim.infrastructure.asr.muaalem import MuaalemRecognizer  # noqa: PLC0415

    container = create_container(await _settings(tmp_path, asr_backend="muaalem"))
    try:
        assert isinstance(await container.get(CardListener), MaroofListener)
        async with container() as request:
            uc = await request.get(AssessRecitation)
            assert isinstance(uc.listener, MaroofListener)
            # решение автора: Muaalem не нужна — не грузится и не создаётся, даже «лениво»
            assert not isinstance(uc.recognizer, MuaalemRecognizer)
    finally:
        await container.close()
    assert loaded.count("maroof") == 1
    assert "muaalem" not in loaded


async def test_sura_scenario_resolves_without_muaalem(tmp_path: Path, loaded: list[str]) -> None:
    """Суры на MostafaMaroof — часть 7 (отдельно). Пока: при ``checker=maroof`` контейнер не
    падает из-за отсутствия ``SuraRecognizer`` у слушателя, ReadSura разрешается, Muaalem не
    грузится. Что ReadSura делает с голосовым до части 7, тест не задаёт."""
    from muallim.application.use_cases.sura import ReadSura  # noqa: PLC0415

    container = create_container(await _settings(tmp_path, asr_backend="muaalem"))
    try:
        async with container() as request:
            assert isinstance(await request.get(ReadSura), ReadSura)
    finally:
        await container.close()
    assert "muaalem" not in loaded


async def test_checker_muaalem_loads_muaalem_and_not_maroof(
    tmp_path: Path, loaded: list[str]
) -> None:
    """Откат настройкой: прежняя модель для всех карточек, слушателя в сценарии нет."""
    settings = await _settings(tmp_path, asr_backend="muaalem", checker="muaalem")
    container = create_container(settings)
    try:
        async with container() as request:
            uc = await request.get(AssessRecitation)
            assert uc.listener is None
    finally:
        await container.close()
    assert "muaalem" in loaded
    assert "maroof" not in loaded


async def test_stub_backend_gives_a_stub_listener(tmp_path: Path, loaded: list[str]) -> None:
    from muallim.infrastructure.asr.stub import StubCardListener  # noqa: PLC0415

    container = create_container(await _settings(tmp_path, asr_backend="stub"))
    try:
        assert isinstance(await container.get(CardListener), StubCardListener)
    finally:
        await container.close()
    assert loaded == []

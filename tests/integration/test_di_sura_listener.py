"""Слушатель суры в контейнере (FR-70 ч. 7, FR-57; ADR-0088 «Суры», ADR-0076 п. 10): при
``checker=maroof`` ``ReadSura`` получает ``MaroofListener`` — тот же объект, что слушает карточки
(одна модель в памяти), а не заглушку-отказ ``DisabledRecognizer``; Muaalem не грузится.
``checker=muaalem`` — слушателя нет, сура по-прежнему на Muaalem. Модели не грузятся: ``load``
подменён.
"""

from pathlib import Path

import pytest
from pydantic import SecretStr

from muallim.application.ports.recognition import CardListener
from muallim.application.use_cases.sura import ReadSura
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
    from muallim.infrastructure.asr.maroof import MaroofListener  # noqa: PLC0415
    from muallim.infrastructure.asr.muaalem import MuaalemRecognizer  # noqa: PLC0415

    calls: list[str] = []
    monkeypatch.setattr(MaroofListener, "load", lambda self: calls.append("maroof"))
    monkeypatch.setattr(MuaalemRecognizer, "load", lambda self: calls.append("muaalem"))
    return calls


async def test_sura_is_heard_by_the_same_maroof_listener_as_cards(
    tmp_path: Path, loaded: list[str]
) -> None:
    from muallim.infrastructure.asr.maroof import MaroofListener  # noqa: PLC0415

    container = create_container(await _settings(tmp_path, asr_backend="muaalem"))
    try:
        cards = await container.get(CardListener)
        async with container() as request:
            uc = await request.get(ReadSura)
            listener = uc.listener
            assert isinstance(listener, MaroofListener)
            assert listener is cards  # одна модель в памяти
    finally:
        await container.close()
    assert loaded.count("maroof") == 1
    assert "muaalem" not in loaded


async def test_checker_muaalem_keeps_the_sura_on_muaalem(tmp_path: Path, loaded: list[str]) -> None:
    settings = await _settings(tmp_path, asr_backend="muaalem", checker="muaalem")
    container = create_container(settings)
    try:
        async with container() as request:
            uc = await request.get(ReadSura)
            assert uc.listener is None
    finally:
        await container.close()
    assert "maroof" not in loaded

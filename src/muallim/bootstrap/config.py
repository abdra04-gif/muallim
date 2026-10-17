"""Настройки из переменных окружения / .env. Шаблон со всеми полями — .env.example."""

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    bot_token: SecretStr
    database_url: SecretStr = SecretStr("sqlite+aiosqlite:///data/dev.sqlite3")
    asr_backend: Literal["muaalem", "stub"] = "muaalem"
    # auto: видеочип Mac (mps) или NVIDIA (cuda), если есть, иначе cpu (mps быстрее в ~10 раз)
    asr_device: Literal["auto", "cpu", "mps", "cuda"] = "auto"
    audio_dir: Path = PROJECT_ROOT / "data" / "audio"
    curriculum_dir: Path = PROJECT_ROOT / "curriculum"
    reference_audio_dir: Path = PROJECT_ROOT / "curriculum" / "audio"
    # Эталон для аятов: чтец EveryAyah (ADR-0025); кэш вне git — data/recitations
    recitations_dir: Path = PROJECT_ROOT / "data" / "recitations"
    reciter: str = "Husary_Muallim_128kbps"
    app_version: str | None = None  # по умолчанию — версия пакета + git-коммит (ADR-0019)
    pass_threshold: int = Field(default=80, ge=0, le=100)
    excellent_threshold: int = Field(default=90, ge=0, le=100)
    log_level: str = "INFO"
    # Telegram ID учителей через запятую: им доступна кнопка «🎙 Записать эталон» (ADR-0024)
    teacher_ids: str = ""

    @property
    def teachers(self) -> frozenset[int]:
        return frozenset(int(x) for x in self.teacher_ids.replace(" ", "").split(",") if x)

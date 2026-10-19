"""Настройки из переменных окружения / .env. Шаблон со всеми полями — .env.example."""

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from muallim.domain.annotation import valid_annotator_code

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    bot_token: SecretStr
    database_url: SecretStr = SecretStr("sqlite+aiosqlite:///data/dev.sqlite3")
    # Вход владельца схемы для миграций (роль muallim_owner, ADR-0054); нет — как у бота
    migration_database_url: SecretStr | None = None
    # Журнал удалений — вне БД: повторяется после восстановления копии (TD-DB-05). По умолчанию
    # рядом с записями (data/erasures/): тесты и консольный режим со своим audio_dir не трогают
    # настоящий журнал.
    erasure_log: Path | None = None
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
    # Файл логов, ротация 3 × 10 МБ (ADR-0048): вне data/, без ПДн; LOG_FILE= — только консоль
    log_file: Path | None = PROJECT_ROOT / "logs" / "bot.log"

    @field_validator("log_file", mode="before")
    @classmethod
    def _empty_log_file_is_none(cls, value: object) -> object:
        return None if value == "" else value

    # Telegram ID учителей через запятую: им доступна кнопка «🎙 Записать эталон» (ADR-0024)
    teacher_ids: str = ""

    # Разметчики в Telegram (FR-17): «код:Telegram ID» через запятую, например «A1:123,A2:456».
    # Отдельно от учителей. Второй путь — приглашение: muallim-research annotator-invite A2
    annotator_ids: str = ""

    @property
    def erasure_log_path(self) -> Path:
        return self.erasure_log or self.audio_dir.parent / "erasures" / "erasures.jsonl"

    def migration_url(self) -> str:
        url = self.migration_database_url or self.database_url
        return url.get_secret_value()

    @property
    def teachers(self) -> frozenset[int]:
        return frozenset(int(x) for x in self.teacher_ids.replace(" ", "").split(",") if x)

    @property
    def annotators(self) -> dict[int, str]:
        found: dict[int, str] = {}
        for pair in self.annotator_ids.replace(" ", "").split(","):
            if not pair:
                continue
            code, _, tg = pair.partition(":")
            if not valid_annotator_code(code) or not tg.isdigit() or int(tg) in found:
                raise ValueError(
                    f"ANNOTATOR_IDS: «{pair}» — нужно «код:Telegram ID» без скобок и кавычек, "
                    "например A1:123456789 (код — латиницей, ID — только цифры, без повторов)"
                )
            found[int(tg)] = code
        return found

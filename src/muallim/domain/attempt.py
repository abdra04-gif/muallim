"""Попытка чтения — основная единица данных исследования.

Хранит не только итог, но и весь путь решения (ADR-0019): все эталоны с баллами, сырые данные
модели, пороги, версии кода, контента и модели, язык объяснения.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from muallim.domain.assessment import Assessment, Candidate
from muallim.domain.policy import GradingPolicy, Verdict


@dataclass(frozen=True, slots=True)
class Attempt:
    id: UUID
    learner_id: UUID
    item_id: str
    curriculum_version: str
    model_version: str  # какая модель и с какими параметрами распознавала
    assessment: Assessment  # по выбранному (лучшему) эталону
    verdict: Verdict
    audio_sha256: str | None  # None — ученик не дал согласия на хранение записи
    audio_duration_ms: int | None
    processing_ms: int
    created_at: datetime
    reference_variant: str = ""  # какой эталон выбран: wasl / waqf
    candidates: tuple[Candidate, ...] = ()  # оценка по каждому эталону
    model_output: Mapping[str, Any] = field(default_factory=dict)  # сырые данные модели
    policy: GradingPolicy = field(default_factory=GradingPolicy)  # пороги на момент решения
    app_version: str = ""  # версия кода (git)
    feedback_language: str = "ru"

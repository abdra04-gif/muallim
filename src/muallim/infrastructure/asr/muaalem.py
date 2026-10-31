"""Распознавание фонем моделью Quran Muaalem (SRC-002).

Модель тяжёлая (~1–2 ГБ), поэтому импортируется лениво и только при ASR_BACKEND=muaalem
(зависимости из extra ``ml``, ADR-0006).
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field, fields, is_dataclass
from functools import lru_cache
from typing import Any, Final

from muallim.application.ports.recognition import (
    PronunciationRecognizer,
    Recognition,
    RecognitionError,
)
from muallim.infrastructure.asr.script import for_phonetizer
from muallim.infrastructure.audio.ffmpeg import SAMPLE_RATE, decode_to_pcm

# Параметры чтения: риваят Хафс, все мадды по 4 харакята. Методическое решение — менять
# только человеку. Строка входит в model_version, поэтому видна в каждой попытке в БД.
MOSHAF_PARAMS: dict[str, Any] = {
    "rewaya": "hafs",
    "madd_monfasel_len": 4,
    "madd_mottasel_len": 4,
    "madd_mottasel_waqf": 4,
    "madd_aared_len": 4,
}
# Ревизия модели obadx/muaalem-model-v3_2 на Hugging Face, на которой сделаны замеры (SRC-003).
# Библиотека берёт последнюю версию; другую замечаем при старте и пишем в лог (TD-FN-121).
EXPECTED_MODEL_REVISION: Final = "01a1ef9fbe40d144ef845101e89ff924aed3fef5"
_UNKNOWN_REVISION: Final = "unknown"

logger: Final = logging.getLogger(__name__)

# Слог, который дописываем, чтобы получить чтение без остановки (васл) — см. ADR-0007.
_WASL_SUFFIX = " مَ"


@dataclass
class MuaalemRecognizer(PronunciationRecognizer):
    device: str = "auto"  # auto | cpu | mps | cuda
    _model: Any = field(default=None, init=False, repr=False)
    _revision: str | None = field(default=None, init=False, repr=False)

    @property
    def model_version(self) -> str:
        """Пишется в каждую попытку (attempts.model_version, ≤ 128 знаков): версия библиотеки,
        короткая ревизия модели (7 знаков, как в git), параметры чтения."""
        params = ",".join(f"{k}={v}" for k, v in MOSHAF_PARAMS.items())
        model = f"@{self._revision[:7]}" if self._revision else ""
        return f"quran-muaalem=={_library_version()}{model};{params}"

    def load(self) -> None:
        """Загрузить и прогреть модель при старте бота, а не на первом голосовом."""
        import numpy as np  # noqa: PLC0415
        import torch  # noqa: PLC0415
        from quran_muaalem import Muaalem  # noqa: PLC0415

        if self.device == "auto":
            self.device = (
                "mps"
                if torch.backends.mps.is_available()
                else "cuda"
                if torch.cuda.is_available()
                else "cpu"
            )
        self._model = Muaalem(device=self.device, dtype=torch.float32)
        self._revision = _loaded_revision(self._model)
        model_ref, _ = _references("بَ")
        self._run(
            np.zeros(SAMPLE_RATE, dtype=np.float32), model_ref
        )  # прогрев: первый вызов долгий

    async def recognize(self, audio: bytes, text: str) -> Recognition:
        import numpy as np  # noqa: PLC0415

        pcm = await decode_to_pcm(audio)
        wave = np.frombuffer(pcm, dtype=np.float32).copy()
        try:
            model_ref, references = _references(text)
            heard, raw = await asyncio.to_thread(self._run, wave, model_ref)
        except Exception as error:  # модель бросает разные исключения на плохом звуке
            raise RecognitionError(str(error)) from error
        return Recognition(
            heard=heard,
            references=references,
            model_version=self.model_version,
            audio_duration_ms=round(len(wave) / SAMPLE_RATE * 1000),
            raw=raw,
        )

    def _run(self, wave: Any, model_ref: Any) -> tuple[str, dict[str, Any]]:
        if self._model is None:
            self.load()
        output = self._model([wave], [model_ref], sampling_rate=SAMPLE_RATE)[0]
        return str(output.phonemes.text), _raw_output(output)


def _library_version() -> str:
    from importlib.metadata import version  # noqa: PLC0415

    return version("quran-muaalem")


def _loaded_revision(model: Any) -> str:
    """Ревизия загруженной модели (коммит на Hugging Face); не та, что ожидали, — в лог."""
    config = getattr(getattr(model, "model", None), "config", None)
    revision = getattr(config, "_commit_hash", None) or _UNKNOWN_REVISION
    if revision != EXPECTED_MODEL_REVISION:
        logger.warning(
            "Модель Muaalem другой ревизии: %s, ожидали %s — цифры могут не совпасть с замерами"
            " (TD-FN-121)",
            revision,
            EXPECTED_MODEL_REVISION,
        )
    else:
        logger.info("Модель Muaalem, ревизия %s", revision)
    return str(revision)


def _raw_output(output: Any) -> dict[str, Any]:
    """Сохраняем всё, что модель отдаёт сверх строки фонем (ADR-0019).

    Выход Muaalem — dataclass'ы (Unit, Sifa, SingleUnit) с тензорами torch. Тензоры → списки
    чисел без округления (признаки B1, ADR-0051; TD-FN-99); неизвестное — строкой, чтобы
    ничего не потерять.
    """
    raw: dict[str, Any] = {"phonemes": str(output.phonemes.text)}
    for name in ("phonemes", "sifat"):
        value = getattr(output, name, None)
        if value is not None:
            raw[f"{name}_full"] = _jsonable(value)
    return raw


def _jsonable(value: Any) -> Any:
    """Объект модели → то, что json.dumps сохранит без потерь."""
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if hasattr(value, "tolist"):  # torch.Tensor, numpy
        return value.tolist()
    if hasattr(value, "model_dump"):
        value = value.model_dump()
    elif is_dataclass(value) and not isinstance(value, type):
        value = {f.name: getattr(value, f.name) for f in fields(value)}
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(v) for v in value]
    try:
        json.dumps(value)
    except TypeError:
        return repr(value)
    return value


@lru_cache(maxsize=1024)
def _references(text: str) -> tuple[Any, tuple[tuple[str, str], tuple[str, str]]]:
    """Эталон для модели и два допустимых варианта: со слитным чтением (васл) и с остановкой.

    Варианты — только из звуков, которые модель умеет выдать: знак мадда «ٓ» над словом, вырезанным
    из аята, фонетизатор оставляет как есть (в аяте за ним шла хамза), а это письмо, не звук.
    """
    from quran_transcript import MoshafAttributes, quran_phonetizer  # noqa: PLC0415

    moshaf = MoshafAttributes(**MOSHAF_PARAMS)
    text = for_phonetizer(text)
    waqf = quran_phonetizer(text, moshaf, remove_spaces=True)
    wasl = quran_phonetizer(text + _WASL_SUFFIX, moshaf, remove_spaces=True).phonemes[:-1]
    sounds = _model_sounds()
    return waqf, (
        ("wasl", "".join(ch for ch in wasl if ch in sounds)),
        ("waqf", "".join(ch for ch in waqf.phonemes if ch in sounds)),
    )


@lru_cache(maxsize=1)
def _model_sounds() -> frozenset[str]:
    """Алфавит фонем модели (quran-transcript): буквы, огласовки, мадд, калькаля, ихфа…"""
    from quran_transcript import alphabet  # noqa: PLC0415

    ph = alphabet.phonetics
    return frozenset("".join(getattr(ph, f.name) for f in fields(ph)))

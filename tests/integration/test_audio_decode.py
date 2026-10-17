"""Декодирование записи: сбой ffmpeg помечается этапом ``decode`` (QAS-04)."""

import shutil

import pytest

from muallim.application.ports.recognition import RecognitionError
from muallim.infrastructure.audio.ffmpeg import decode_to_pcm

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="нет ffmpeg"),
]


async def test_broken_audio_fails_at_decode_stage() -> None:
    with pytest.raises(RecognitionError) as error:
        await decode_to_pcm(b"not an ogg file")
    assert error.value.stage == "decode"

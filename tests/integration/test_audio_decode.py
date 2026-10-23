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


async def test_trim_silence_cuts_quiet_edges_and_keeps_the_sound(tmp_path: object) -> None:
    """1 с тишины + 0,5 с тона + 1 с тишины → около 0,5 с; сломанный файл возвращается как был."""
    import asyncio  # noqa: PLC0415

    from muallim.infrastructure.audio.ffmpeg import trim_silence  # noqa: PLC0415

    async def run(*args: str, data: bytes = b"") -> bytes:
        proc = await asyncio.create_subprocess_exec(
            *args, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE
        )
        out, _ = await proc.communicate(data)
        return out

    mp3 = await run(
        "ffmpeg", "-v", "quiet", "-f", "lavfi", "-i",
        "anullsrc=r=44100:cl=mono:d=1[s1];sine=f=440:d=0.5:r=44100[t];"
        "anullsrc=r=44100:cl=mono:d=1[s2];[s1][t][s2]concat=n=3:v=0:a=1",
        "-c:a", "libmp3lame", "-f", "mp3", "pipe:1",
    )  # fmt: skip
    trimmed = await trim_silence(mp3)

    async def seconds(audio: bytes) -> float:
        return len(await decode_to_pcm(audio)) / 4 / 16_000  # float32, 16 кГц

    assert await seconds(mp3) > 2.4
    assert 0.4 < await seconds(trimmed) < 0.9
    assert await trim_silence(b"not audio") == b"not audio"

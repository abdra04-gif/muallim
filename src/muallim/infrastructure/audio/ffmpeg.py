"""Декодирование голосового из Telegram (OGG/Opus) в 16 кГц моно float32 через ffmpeg."""

import asyncio
from typing import Final

from muallim.application.ports.recognition import RecognitionError

SAMPLE_RATE: Final[int] = 16_000
MAX_SECONDS: Final[int] = 60  # защита от огромных файлов (NFR-SEC-05)


async def decode_to_pcm(audio: bytes) -> bytes:
    """Возвращает сырые float32 little-endian сэмплы."""
    process = await asyncio.create_subprocess_exec(
        "ffmpeg", "-nostdin", "-loglevel", "error", "-i", "pipe:0",
        "-t", str(MAX_SECONDS), "-f", "f32le", "-ac", "1", "-ar", str(SAMPLE_RATE), "pipe:1",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )  # fmt: skip
    stdout, stderr = await process.communicate(audio)
    if process.returncode != 0:
        message = f"ffmpeg: {stderr.decode(errors='replace').strip()[:200]}"
        raise RecognitionError(message, stage="decode")
    if not stdout:
        raise RecognitionError("Пустая запись", stage="decode")
    return stdout


# Тишина по краям эталона: тише −45 дБ дольше 0,1 с; 0,1 с оставляем, чтобы не срезать начало звука.
_EDGE = "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.1"
_TRIM = f"{_EDGE},areverse,{_EDGE},areverse"


async def trim_silence(audio: bytes) -> bytes:
    """MP3 без тишины в начале и в конце; если ffmpeg не справился — исходный файл."""
    process = await asyncio.create_subprocess_exec(
        "ffmpeg", "-nostdin", "-loglevel", "error", "-i", "pipe:0", "-af", _TRIM,
        "-c:a", "libmp3lame", "-q:a", "2", "-f", "mp3", "pipe:1",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )  # fmt: skip
    stdout, _ = await process.communicate(audio)
    return stdout if process.returncode == 0 and stdout else audio

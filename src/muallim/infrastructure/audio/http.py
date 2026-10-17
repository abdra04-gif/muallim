"""Скачивание файлов по HTTPS (aiohttp — уже есть как зависимость aiogram)."""

import aiohttp

TIMEOUT = aiohttp.ClientTimeout(total=20)


async def fetch(url: str) -> bytes:
    async with aiohttp.ClientSession(timeout=TIMEOUT) as session, session.get(url) as response:
        response.raise_for_status()
        return await response.read()

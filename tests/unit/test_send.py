"""Отправка экрана: результат с ошибками — фото и вторым сообщением объяснения (FR-43)."""

from dataclasses import dataclass, field
from typing import Any

from aiogram.types import InlineKeyboardMarkup

from muallim.presentation.telegram import handlers
from muallim.presentation.telegram.screens import Screen

KB = InlineKeyboardMarkup(inline_keyboard=[])


@dataclass
class _Sent:
    message_id: int
    photo: list[Any] = field(default_factory=list)


@dataclass
class FakeBot:
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    async def send_photo(self, chat_id: int, photo: Any, **kw: Any) -> _Sent:
        self.calls.append(("photo", kw))
        return _Sent(len(self.calls))

    async def send_message(self, chat_id: int, text: str, **kw: Any) -> _Sent:
        self.calls.append(("text", {"text": text, **kw}))
        return _Sent(len(self.calls))

    async def edit_message_reply_markup(self, **kw: Any) -> None:
        self.calls.append(("retire", kw))


async def test_details_go_to_second_message_with_buttons() -> None:
    bot = FakeBot()
    await handlers.send(bot, 7, Screen("подпись", KB, b"png", details="объяснения"))  # type: ignore[arg-type]
    (kind1, photo), (kind2, text) = bot.calls[:2]
    assert kind1 == "photo" and photo.get("reply_markup") is None and photo["caption"] == "подпись"
    assert kind2 == "text" and text["text"] == "объяснения" and text["reply_markup"] is KB


async def test_screen_without_details_is_one_message() -> None:
    bot = FakeBot()
    await handlers.send(bot, 8, Screen("подпись", KB, b"png"))  # type: ignore[arg-type]
    assert [k for k, _ in bot.calls] == ["photo"]
    assert bot.calls[0][1]["reply_markup"] is KB

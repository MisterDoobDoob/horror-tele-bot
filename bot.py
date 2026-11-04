import asyncio
import json
import logging
import os
from typing import Any
from urllib import parse, request


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


class TelegramPasskeyBot:
    def __init__(self, token: str, passkey: str) -> None:
        self._token = token
        self._passkey = passkey
        self._base_url = f"https://api.telegram.org/bot{token}"
        self._offset = 0

    async def _api_request(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._base_url}/{method}"

        def _send() -> dict[str, Any]:
            data = parse.urlencode(payload).encode("utf-8")
            req = request.Request(url, data=data)
            with request.urlopen(req, timeout=35) as response:
                return json.loads(response.read().decode("utf-8"))

        return await asyncio.to_thread(_send)

    async def get_updates(self) -> list[dict[str, Any]]:
        result = await self._api_request(
            "getUpdates",
            {"offset": self._offset, "timeout": 30, "allowed_updates": json.dumps(["message"])},
        )
        if not result.get("ok"):
            raise RuntimeError(f"Telegram getUpdates failed: {result}")
        return result.get("result", [])

    async def send_message(self, chat_id: int, text: str) -> None:
        result = await self._api_request("sendMessage", {"chat_id": chat_id, "text": text})
        if not result.get("ok"):
            raise RuntimeError(f"Telegram sendMessage failed: {result}")

    async def handle_update(self, update: dict[str, Any]) -> None:
        update_id = update.get("update_id")
        if isinstance(update_id, int):
            self._offset = update_id + 1

        message = update.get("message")
        if not isinstance(message, dict):
            return

        chat = message.get("chat")
        chat_id = chat.get("id") if isinstance(chat, dict) else None
        text = message.get("text")

        if not isinstance(chat_id, int) or not isinstance(text, str):
            return

        if text.strip() == self._passkey:
            await self.send_message(chat_id, "Passkey accepted ✅")
        else:
            await self.send_message(chat_id, "Invalid passkey ❌")

    async def run(self) -> None:
        logging.info("Bot started and waiting for passkeys")
        while True:
            try:
                updates = await self.get_updates()
                for update in updates:
                    await self.handle_update(update)
            except Exception as error:  # pragma: no cover
                logging.exception("Polling error: %s", error)
                await asyncio.sleep(2)


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


async def main() -> None:
    token = _required_env("TELEGRAM_BOT_TOKEN")
    passkey = _required_env("TELEGRAM_PASSKEY")
    bot = TelegramPasskeyBot(token=token, passkey=passkey)
    await bot.run()


if __name__ == "__main__":
    asyncio.run(main())

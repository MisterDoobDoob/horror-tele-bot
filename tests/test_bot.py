import unittest

from bot import TelegramPasskeyBot


class StubBot(TelegramPasskeyBot):
    def __init__(self, passkey: str) -> None:
        super().__init__(token="token", passkey=passkey)
        self.sent_messages = []

    async def send_message(self, chat_id: int, text: str) -> None:
        self.sent_messages.append((chat_id, text))


class PasskeyBotTests(unittest.IsolatedAsyncioTestCase):
    async def test_accepts_matching_passkey(self) -> None:
        bot = StubBot(passkey="open-sesame")
        update = {
            "update_id": 1,
            "message": {"chat": {"id": 123}, "text": "open-sesame"},
        }

        await bot.handle_update(update)

        self.assertEqual(bot.sent_messages, [(123, "Passkey accepted ✅")])

    async def test_rejects_invalid_passkey(self) -> None:
        bot = StubBot(passkey="open-sesame")
        update = {
            "update_id": 2,
            "message": {"chat": {"id": 123}, "text": "wrong-key"},
        }

        await bot.handle_update(update)

        self.assertEqual(bot.sent_messages, [(123, "Invalid passkey ❌")])


if __name__ == "__main__":
    unittest.main()

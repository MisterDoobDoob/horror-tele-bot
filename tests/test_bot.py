import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from bot import (
    CAPTION_LIMIT,
    Reply,
    TelegramPasskeyBot,
    _encode_multipart,
    detect_file_type,
    load_env_file,
    load_invalid_reply,
    load_passkey_responses,
)


class StubBot(TelegramPasskeyBot):
    def __init__(self, responses: dict[str, Reply], **kwargs) -> None:
        super().__init__(token="token", responses=responses, **kwargs)
        self.sent = []

    async def send_message(self, chat_id: int, text: str) -> None:
        self.sent.append(("text", chat_id, text))

    async def send_file(
        self, chat_id: int, file: str, file_type: str, caption: str | None = None
    ) -> None:
        self.sent.append(("file", chat_id, file, file_type, caption))


def _update(update_id: int, text: str) -> dict:
    return {"update_id": update_id, "message": {"chat": {"id": 123}, "text": text}}


class PasskeyBotTests(unittest.IsolatedAsyncioTestCase):
    async def test_each_passkey_gets_its_own_response(self) -> None:
        bot = StubBot({"alpha": Reply(text="Response A"), "beta": Reply(text="Response B")})

        await bot.handle_update(_update(1, "alpha"))
        await bot.handle_update(_update(2, "  beta  "))

        self.assertEqual(bot.sent, [("text", 123, "Response A"), ("text", 123, "Response B")])

    async def test_rejects_invalid_passkey(self) -> None:
        bot = StubBot({"alpha": Reply(text="Response A")})
        await bot.handle_update(_update(3, "wrong-key"))
        self.assertEqual(bot.sent, [("text", 123, "Invalid passkey ❌")])

    async def test_custom_invalid_reply(self) -> None:
        bot = StubBot({"alpha": Reply(text="A")}, invalid_reply=Reply(text="Nope.", file="no.png"))
        await bot.handle_update(_update(4, "wrong-key"))
        self.assertEqual(bot.sent, [("file", 123, "no.png", "photo", "Nope.")])

    async def test_file_with_caption(self) -> None:
        bot = StubBot({"alpha": Reply(text="Boo", file="https://x/y.gif?v=2")})
        await bot.handle_update(_update(5, "alpha"))
        self.assertEqual(bot.sent, [("file", 123, "https://x/y.gif?v=2", "animation", "Boo")])

    async def test_file_id_defaults_to_document(self) -> None:
        bot = StubBot({"alpha": Reply(file="file-id-123")})
        await bot.handle_update(_update(6, "alpha"))
        self.assertEqual(bot.sent, [("file", 123, "file-id-123", "document", None)])

    async def test_explicit_file_type_overrides_detection(self) -> None:
        bot = StubBot({"alpha": Reply(file="file-id-123", file_type="video")})
        await bot.handle_update(_update(7, "alpha"))
        self.assertEqual(bot.sent, [("file", 123, "file-id-123", "video", None)])

    async def test_long_text_sent_separately_from_file(self) -> None:
        long_text = "x" * (CAPTION_LIMIT + 1)
        bot = StubBot({"alpha": Reply(text=long_text, file="f.pdf")})
        await bot.handle_update(_update(8, "alpha"))
        self.assertEqual(
            bot.sent, [("file", 123, "f.pdf", "document", None), ("text", 123, long_text)]
        )


class ConfigTests(unittest.TestCase):
    def test_load_passkey_responses_pairs_by_suffix(self) -> None:
        env = {
            "PASSKEY_1": "a",
            "RESPONSE_1": "A",
            "PASSKEY_2": "b",
            "FILE_2": "https://x/b.mp3",
            "FILE_TYPE_2": "Voice",
        }
        self.assertEqual(
            load_passkey_responses(env),
            {"a": Reply(text="A"), "b": Reply(file="https://x/b.mp3", file_type="voice")},
        )

    def test_missing_response_and_file_raises(self) -> None:
        with self.assertRaises(RuntimeError):
            load_passkey_responses({"PASSKEY_1": "a"})

    def test_missing_local_file_raises(self) -> None:
        with self.assertRaises(RuntimeError):
            load_passkey_responses({"PASSKEY_1": "a", "FILE_1": "media/does-not-exist.pdf"})

    def test_unknown_file_type_raises(self) -> None:
        with self.assertRaises(RuntimeError):
            load_passkey_responses({"PASSKEY_1": "a", "FILE_1": "id", "FILE_TYPE_1": "sticker"})

    def test_detect_file_type(self) -> None:
        self.assertEqual(detect_file_type("a/b.JPG"), "photo")
        self.assertEqual(detect_file_type("clip.mp4"), "video")
        self.assertEqual(detect_file_type("song.mp3"), "audio")
        self.assertEqual(detect_file_type("note.ogg"), "voice")
        self.assertEqual(detect_file_type("https://x/doc.pdf?dl=1"), "document")

    def test_no_passkeys_raises(self) -> None:
        with self.assertRaises(RuntimeError):
            load_passkey_responses({})

    def test_invalid_reply_defaults(self) -> None:
        self.assertEqual(load_invalid_reply({}).text, "Invalid passkey ❌")

    def test_multipart_includes_file_and_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "spooky.gif"
            path.write_bytes(b"GIF89a-data")
            body, content_type = _encode_multipart({"chat_id": 1}, {"animation": path})
        self.assertIn("multipart/form-data; boundary=", content_type)
        self.assertIn(b'name="chat_id"\r\n\r\n1', body)
        self.assertIn(b'filename="spooky.gif"\r\nContent-Type: image/gif', body)
        self.assertIn(b"GIF89a-data", body)

    def test_load_env_file_parses_quotes_and_newlines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text(
                "# comment\n"
                "TEST_PLAIN=hello\n"
                'TEST_DOUBLE="line one\\nline two"\n'
                "export TEST_SINGLE='raw\\n'\n",
                encoding="utf-8",
            )
            with mock.patch.dict(os.environ, {}, clear=True):
                load_env_file(path)
                self.assertEqual(os.environ["TEST_PLAIN"], "hello")
                self.assertEqual(os.environ["TEST_DOUBLE"], "line one\nline two")
                self.assertEqual(os.environ["TEST_SINGLE"], "raw\\n")


if __name__ == "__main__":
    unittest.main()

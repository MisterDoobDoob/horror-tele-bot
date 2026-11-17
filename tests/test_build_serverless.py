import tempfile
import unittest
from pathlib import Path

from bot import Reply
from build_serverless import FileUploader, _serialize_reply, build_config, render_config


class StubBot:
    def __init__(self) -> None:
        self.calls = []

    async def _api_request(self, method, payload, files=None):
        self.calls.append((method, payload, files))
        if method == "deleteMessage":
            return {"ok": True, "result": True}
        return {
            "ok": True,
            "result": {"message_id": 7, "photo": [{"file_id": "small"}, {"file_id": "large"}]},
        }


class BuildServerlessTests(unittest.IsolatedAsyncioTestCase):
    async def test_build_config_text_and_url(self) -> None:
        env = {
            "PASSKEY_1": " alpha ",
            "RESPONSE_1": "A",
            "PASSKEY_2": "beta",
            "FILE_2": "https://example.com/door.jpg",
            "INVALID_RESPONSE": "nope",
        }
        config = await build_config(env, {})
        self.assertEqual(
            config,
            {
                "responses": {
                    "alpha": {"text": "A"},
                    "beta": {"file": "https://example.com/door.jpg", "type": "photo"},
                },
                "invalid": {"text": "nope"},
            },
        )

    async def test_build_config_launch(self) -> None:
        env = {
            "PASSKEY_1": "alpha",
            "RESPONSE_1": "A",
            "UNLOCK_AT": "2026-11-18T14:00:00+08:00",
            "LOCKED_RESPONSE": "Locked.",
            "WELCOME_RESPONSE": "Welcome.",
            "VENUE_VIDEO": "https://x/venue.mp4",
            "WEBSITE_URL": "https://example.com",
        }
        config = await build_config(env, {})
        self.assertEqual(
            config["launch"],
            {
                "unlockAt": 1795413600000,  # 2026-11-18T06:00:00Z
                "locked": {"text": "Locked."},
                "welcome": "Welcome.",
                "venueVideo": {"file": "https://x/venue.mp4", "type": "video"},
                "websiteUrl": "https://example.com",
            },
        )

    async def test_local_file_requires_upload_chat(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".jpg") as tmp:
            env = {"PASSKEY_1": "a", "FILE_1": tmp.name, "TELEGRAM_BOT_TOKEN": "1:x"}
            with self.assertRaisesRegex(RuntimeError, "UPLOAD_CHAT_ID"):
                await build_config(env, {})

    async def test_uploader_uses_largest_photo_and_caches(self) -> None:
        bot = StubBot()
        cache: dict = {}
        uploader = FileUploader(bot, "1", "42", cache)
        with tempfile.NamedTemporaryFile(suffix=".jpg") as tmp:
            reply = Reply(text="boo", file=tmp.name)
            first = await _serialize_reply(reply, uploader)
            second = await _serialize_reply(reply, uploader)

        self.assertEqual(first, {"text": "boo", "file": "large", "type": "photo"})
        self.assertEqual(second, first)
        self.assertEqual([c[0] for c in bot.calls], ["sendPhoto", "deleteMessage"])  # uploaded once
        self.assertEqual(bot.calls[0][2], {"photo": Path(tmp.name)})
        self.assertEqual(list(cache), ["1"])

    def test_render_config_is_js_module(self) -> None:
        js = render_config({"responses": {"ключ": {"text": 'a "q"\nb'}}, "invalid": {}})
        self.assertIn('export default {', js)
        self.assertIn('"ключ"', js)
        self.assertIn('"a \\"q\\"\\nb"', js)
        self.assertTrue(js.endswith("};\n"))


if __name__ == "__main__":
    unittest.main()

import asyncio
import json
import logging
import mimetypes
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib import parse, request


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"
CAPTION_LIMIT = 1024  # Telegram's max caption length for media

# file type -> (Telegram method, form field name)
FILE_TYPES: dict[str, tuple[str, str]] = {
    "photo": ("sendPhoto", "photo"),
    "animation": ("sendAnimation", "animation"),
    "video": ("sendVideo", "video"),
    "audio": ("sendAudio", "audio"),
    "voice": ("sendVoice", "voice"),
    "document": ("sendDocument", "document"),
}

EXTENSION_TYPES: dict[str, str] = {
    ".jpg": "photo", ".jpeg": "photo", ".png": "photo", ".webp": "photo",
    ".gif": "animation",
    ".mp4": "video", ".mov": "video", ".webm": "video", ".mkv": "video",
    ".mp3": "audio", ".m4a": "audio", ".wav": "audio", ".flac": "audio",
    ".ogg": "voice", ".oga": "voice",
}


def detect_file_type(file: str) -> str:
    """Guess the Telegram file type from a path or URL extension. Defaults to document."""
    path = parse.urlparse(file).path if file.startswith(("http://", "https://")) else file
    return EXTENSION_TYPES.get(Path(path).suffix.lower(), "document")


@dataclass(frozen=True)
class Reply:
    text: str | None = None
    file: str | None = None  # URL, Telegram file_id, or local file path
    file_type: str | None = None  # key of FILE_TYPES; auto-detected when None

    def resolved_file_type(self) -> str:
        return self.file_type or detect_file_type(self.file or "")


DEFAULT_INVALID_REPLY = Reply(text="Invalid passkey ❌")
DEFAULT_WELCOME_TEXT = "Welcome! The game hasn't started yet."

VENUE_VIDEO_CALLBACK = "venue_video"
VENUE_VIDEO_BUTTON = "🎬 How to get to the venue"
WEBSITE_BUTTON = "🌐 Visit the website"


@dataclass(frozen=True)
class Launch:
    """Pre-game behaviour, active until unlock_at."""

    unlock_at: datetime  # timezone-aware
    locked_reply: Reply  # replaces the invalid reply until unlock_at
    welcome_text: str = DEFAULT_WELCOME_TEXT  # reply to /start until unlock_at
    venue_video: Reply | None = None  # sent when the venue button is tapped
    website_url: str | None = None

    def welcome_markup(self) -> dict[str, Any] | None:
        rows = []
        if self.venue_video:
            rows.append([{"text": VENUE_VIDEO_BUTTON, "callback_data": VENUE_VIDEO_CALLBACK}])
        if self.website_url:
            rows.append([{"text": WEBSITE_BUTTON, "url": self.website_url}])
        return {"inline_keyboard": rows} if rows else None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TelegramPasskeyBot:
    def __init__(
        self,
        token: str,
        responses: dict[str, Reply],
        invalid_reply: Reply = DEFAULT_INVALID_REPLY,
        launch: Launch | None = None,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._token = token
        self._responses = responses
        self._invalid_reply = invalid_reply
        self._launch = launch
        self._clock = clock
        self._base_url = f"https://api.telegram.org/bot{token}"
        self._offset = 0

    def _is_locked(self) -> bool:
        return self._launch is not None and self._clock() < self._launch.unlock_at

    async def _api_request(
        self,
        method: str,
        payload: dict[str, Any],
        files: dict[str, Path] | None = None,
    ) -> dict[str, Any]:
        url = f"{self._base_url}/{method}"

        def _send() -> dict[str, Any]:
            if files:
                data, content_type = _encode_multipart(payload, files)
                req = request.Request(url, data=data, headers={"Content-Type": content_type})
            else:
                req = request.Request(url, data=parse.urlencode(payload).encode("utf-8"))
            with request.urlopen(req, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))

        return await asyncio.to_thread(_send)

    async def get_updates(self) -> list[dict[str, Any]]:
        result = await self._api_request(
            "getUpdates",
            {
                "offset": self._offset,
                "timeout": 30,
                "allowed_updates": json.dumps(["message", "callback_query"]),
            },
        )
        if not result.get("ok"):
            raise RuntimeError(f"Telegram getUpdates failed: {result}")
        return result.get("result", [])

    async def send_message(
        self, chat_id: int, text: str, reply_markup: dict[str, Any] | None = None
    ) -> None:
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text}
        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup)
        result = await self._api_request("sendMessage", payload)
        if not result.get("ok"):
            raise RuntimeError(f"Telegram sendMessage failed: {result}")

    async def answer_callback_query(self, callback_query_id: str) -> None:
        result = await self._api_request(
            "answerCallbackQuery", {"callback_query_id": callback_query_id}
        )
        if not result.get("ok"):
            raise RuntimeError(f"Telegram answerCallbackQuery failed: {result}")

    async def send_file(
        self, chat_id: int, file: str, file_type: str, caption: str | None = None
    ) -> None:
        method, field = FILE_TYPES[file_type]
        payload: dict[str, Any] = {"chat_id": chat_id}
        if caption:
            payload["caption"] = caption

        path = _resolve_local_file(file)
        if path is not None:
            result = await self._api_request(method, payload, files={field: path})
        else:
            payload[field] = file  # URL or Telegram file_id
            result = await self._api_request(method, payload)

        if not result.get("ok"):
            raise RuntimeError(f"Telegram {method} failed: {result}")

    async def send_reply(self, chat_id: int, reply: Reply) -> None:
        if not reply.file:
            if reply.text:
                await self.send_message(chat_id, reply.text)
            return

        file_type = reply.resolved_file_type()
        if reply.text and len(reply.text) > CAPTION_LIMIT:
            # Too long for a caption: send the file, then the text separately.
            await self.send_file(chat_id, reply.file, file_type)
            await self.send_message(chat_id, reply.text)
        else:
            await self.send_file(chat_id, reply.file, file_type, caption=reply.text)

    async def handle_update(self, update: dict[str, Any]) -> None:
        update_id = update.get("update_id")
        if isinstance(update_id, int):
            self._offset = update_id + 1

        callback_query = update.get("callback_query")
        if isinstance(callback_query, dict):
            await self.handle_callback_query(callback_query)
            return

        message = update.get("message")
        if not isinstance(message, dict):
            return

        chat = message.get("chat")
        chat_id = chat.get("id") if isinstance(chat, dict) else None
        text = message.get("text")

        if not isinstance(chat_id, int) or not isinstance(text, str):
            return

        text = text.strip()
        locked = self._is_locked()
        if locked and self._launch and _is_start_command(text):
            await self.send_message(
                chat_id, self._launch.welcome_text, self._launch.welcome_markup()
            )
            return

        reply = self._responses.get(text)
        if reply is None:
            reply = self._launch.locked_reply if locked and self._launch else self._invalid_reply
        await self.send_reply(chat_id, reply)

    async def handle_callback_query(self, callback_query: dict[str, Any]) -> None:
        query_id = callback_query.get("id")
        if isinstance(query_id, str):
            await self.answer_callback_query(query_id)  # stops the button's loading spinner

        message = callback_query.get("message")
        chat = message.get("chat") if isinstance(message, dict) else None
        chat_id = chat.get("id") if isinstance(chat, dict) else None
        if not isinstance(chat_id, int):
            return

        if (
            callback_query.get("data") == VENUE_VIDEO_CALLBACK
            and self._launch
            and self._launch.venue_video
        ):
            await self.send_reply(chat_id, self._launch.venue_video)

    async def run(self) -> None:
        logging.info("Bot started with %d passkey(s)", len(self._responses))
        while True:
            try:
                updates = await self.get_updates()
                for update in updates:
                    await self.handle_update(update)
            except Exception as error:  # pragma: no cover
                logging.exception("Polling error: %s", error)
                await asyncio.sleep(2)


def _is_start_command(text: str) -> bool:
    """True for /start, /start <payload> and /start@BotName."""
    command = text.split(maxsplit=1)[0] if text else ""
    return command.split("@", 1)[0] == "/start"


def _resolve_local_file(value: str) -> Path | None:
    """Return a Path if value points to an existing local file (relative to bot.py)."""
    if value.startswith(("http://", "https://")):
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = BASE_DIR / path
    return path if path.is_file() else None


def _encode_multipart(fields: dict[str, Any], files: dict[str, Path]) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
        )
    for name, path in files.items():
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        header = (
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; '
            f'filename="{path.name}"\r\nContent-Type: {mime}\r\n\r\n'
        )
        parts.append(header.encode() + path.read_bytes() + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def load_env_file(path: Path) -> None:
    """Load KEY=VALUE lines from a .env file into os.environ.

    Variables already set in the real environment take precedence.
    Double-quoted values support \\n for multi-line responses.
    """
    if not path.is_file():
        return

    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        if "=" not in line:
            logging.warning("Ignoring malformed line %d in %s", line_number, path.name)
            continue

        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()

        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            quote = value[0]
            value = value[1:-1]
            if quote == '"':
                value = value.replace("\\n", "\n").replace('\\"', '"')

        os.environ.setdefault(key, value)


def _load_reply(env: Mapping[str, str], text_key: str, file_key: str, type_key: str) -> Reply | None:
    """Build a Reply from env keys, validating the file settings. None if nothing is set."""
    text = env.get(text_key) or None
    file = (env.get(file_key) or "").strip() or None
    file_type = (env.get(type_key) or "").strip().lower() or None
    if not text and not file:
        return None

    if file_type and file_type not in FILE_TYPES:
        raise RuntimeError(f"{type_key} must be one of: {', '.join(FILE_TYPES)}")

    # Fail fast if the file looks like a local path but doesn't exist.
    # (Telegram file_ids contain no dots or slashes, so they're skipped.)
    if file and not file.startswith(("http://", "https://")):
        looks_like_path = "/" in file or "\\" in file or "." in file
        if looks_like_path and _resolve_local_file(file) is None:
            raise RuntimeError(f"{file_key} points to a file that doesn't exist: {file}")

    return Reply(text=text, file=file, file_type=file_type)


def load_passkey_responses(env: Mapping[str, str] = os.environ) -> dict[str, Reply]:
    """Collect PASSKEY_<n> with RESPONSE_<n> and/or FILE_<n> from the environment."""
    responses: dict[str, Reply] = {}
    pattern = re.compile(r"^PASSKEY_(\w+)$")

    for key, passkey in env.items():
        match = pattern.match(key)
        if not match:
            continue
        suffix = match.group(1)
        passkey = passkey.strip()
        if not passkey:
            continue
        reply = _load_reply(env, f"RESPONSE_{suffix}", f"FILE_{suffix}", f"FILE_TYPE_{suffix}")
        if reply is None:
            raise RuntimeError(f"{key} is set but neither RESPONSE_{suffix} nor FILE_{suffix} is")
        if passkey in responses:
            raise RuntimeError(f"Duplicate passkey value found in {key}")
        responses[passkey] = reply

    if not responses:
        raise RuntimeError("No passkeys configured. Add PASSKEY_1 / RESPONSE_1 to your .env file")
    return responses


def load_invalid_reply(env: Mapping[str, str] = os.environ) -> Reply:
    reply = _load_reply(env, "INVALID_RESPONSE", "INVALID_FILE", "INVALID_FILE_TYPE")
    return reply or DEFAULT_INVALID_REPLY


def load_launch(env: Mapping[str, str] = os.environ) -> Launch | None:
    """Pre-game settings. None when UNLOCK_AT isn't set."""
    raw = (env.get("UNLOCK_AT") or "").strip()
    if not raw:
        return None
    try:
        unlock_at = datetime.fromisoformat(raw)
    except ValueError as error:
        raise RuntimeError(f"UNLOCK_AT is not an ISO 8601 date-time: {raw}") from error
    if unlock_at.tzinfo is None:
        raise RuntimeError("UNLOCK_AT needs a timezone offset, e.g. 2026-11-18T14:00:00+08:00")

    website_url = (env.get("WEBSITE_URL") or "").strip() or None
    if website_url and not website_url.startswith(("http://", "https://")):
        raise RuntimeError("WEBSITE_URL must start with http:// or https://")

    locked = _load_reply(env, "LOCKED_RESPONSE", "LOCKED_FILE", "LOCKED_FILE_TYPE")
    return Launch(
        unlock_at=unlock_at,
        locked_reply=locked or load_invalid_reply(env),
        welcome_text=env.get("WELCOME_RESPONSE") or DEFAULT_WELCOME_TEXT,
        venue_video=_load_reply(env, "VENUE_VIDEO_CAPTION", "VENUE_VIDEO", "VENUE_VIDEO_TYPE"),
        website_url=website_url,
    )


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


async def main() -> None:
    load_env_file(ENV_FILE)
    token = _required_env("TELEGRAM_BOT_TOKEN")
    bot = TelegramPasskeyBot(
        token=token,
        responses=load_passkey_responses(),
        invalid_reply=load_invalid_reply(),
        launch=load_launch(),
    )
    await bot.run()


if __name__ == "__main__":
    asyncio.run(main())

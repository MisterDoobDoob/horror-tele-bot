# horror-tele-bot

Minimal Telegram bot in Python + `asyncio` that replies to passkeys. Each passkey has its own response, and is stored in .env

## Behavior

- Passkeys and replies are paired by suffix: `PASSKEY_<n>` → `RESPONSE_<n>` and/or `FILE_<n>`. Add as many as you like.
- If a message (trimmed) exactly matches a passkey, the bot sends that passkey's reply.
- Otherwise it sends `INVALID_RESPONSE` / `INVALID_FILE` from .env (default `Invalid passkey ❌`).
- Real environment variables will override values in `.env`.

## Local Setup

1. Create a Telegram bot and get the bot token.
2. Copy the example config and fill in your values:

```bash
cp .env.example .env
```

```dotenv
TELEGRAM_BOT_TOKEN=<your-bot-token>

PASSKEY_1=first-secret
RESPONSE_1="Reply for the first passkey"

PASSKEY_2=second-secret
RESPONSE_2="Multi-line reply\nuse \n inside double quotes"
FILE_2=https://example.com/scary.jpg

PASSKEY_3=third-secret
FILE_3=media/jumpscare.mp4

# Optional
INVALID_RESPONSE="Invalid passkey ❌"
INVALID_FILE=media/nope.gif
```

`.env` is gitignored, so passkeys and responses are never committed. Only `.env.example` is tracked.

3. Run the bot:

```bash
python bot.py
```

### Or: host it on Telegram Serverless (no server needed, invite needed)

1. In @BotFather, open your bot → **Serverless**, turn it on, and copy the CLI access token.
2. Copy the example .env config and fill in your values in 
```bash
cp .env.example .env
```

```dotenv
TELEGRAM_BOT_TOKEN=<your-bot-token>

PASSKEY_1=first-secret
RESPONSE_1="Reply for the first passkey"
...

INVALID_FILE=media/nope.gif
```

4. Run:

```bash
npm install
npx tgcloud login
npm run deploy
```

3. Run `npm run deploy` again whenever you change `.env`.
4. If you want to upload local files, set `UPLOAD_CHAT_ID` in `.env` first (see `.env.example`).

```dotenv
UPLOAD_CHAT_ID=<your-user-id>
```

6. Don't also run `python bot.py` for the same bot. 

### Files

File size limit is 30MB, I used local file upload for this... rest is untested

`FILE_<n>` can be a URL, a local file path (relative to `bot.py`), or a Telegram `file_id`. If a `RESPONSE_<n>` is also set, it becomes the file's caption. Captions over 1024 characters are sent as a separate message after the file.

How the file is shown in Telegram is picked from its extension:

| Type | Extensions |
| --- | --- |
| `photo` | `.jpg` `.jpeg` `.png` `.webp` |
| `animation` | `.gif` |
| `video` | `.mp4` `.mov` `.webm` `.mkv` |
| `audio` | `.mp3` `.m4a` `.wav` `.flac` |
| `voice` | `.ogg` `.oga` |
| `document` | anything else (downloadable file) |

Set `FILE_TYPE_<n>` (or `INVALID_FILE_TYPE`) to one of these types to override the guess. You need this for `file_id`s, since they have no extension.

## Tests

```bash
python -m unittest discover tests
npm test
```

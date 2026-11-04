# horror-tele-bot

Minimal Telegram bot in Python + `asyncio` that responds to a passkey.

## Setup

1. Create a Telegram bot and get the bot token.
2. Export required environment variables:

```bash
export TELEGRAM_BOT_TOKEN="<your-bot-token>"
export TELEGRAM_PASSKEY="<your-passkey>"
```

3. Run the bot:

```bash
python bot.py
```

## Behavior

- If a user sends a message exactly matching `TELEGRAM_PASSKEY`, the bot replies with `Passkey accepted ✅`.
- Otherwise, the bot replies with `Invalid passkey ❌`.

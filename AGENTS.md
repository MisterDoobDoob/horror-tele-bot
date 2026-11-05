# AGENTS.md

Notes for coding agents/humans. For users, see README.md.

## What this is

A Telegram bot that answers passkeys. If a message (trimmed) exactly matches a passkey, the bot sends that passkey's reply: text, a file, or a file with the text as its caption. Any other text gets the "invalid" reply. Messages without text are ignored.

The bot can run in two ways, and both read the same `.env`:

| Mode | Code | How it gets updates |
| --- | --- | --- |
| Self-hosted | `bot.py` (Python stdlib, asyncio) | Long polling with `getUpdates` |
| Telegram Serverless | `tgcloud/` (JavaScript) | Webhook managed by the platform |

Don't run both for the same bot. Serverless owns the webhook, and `getUpdates` fails while a webhook is set.

## Layout

```
bot.py                     self-hosted bot, plus the .env parsing used by the build script
build_serverless.py        .env -> tgcloud/lib/config.js (uploads local files)
tgcloud/                   the only folder deployed to Serverless
  handlers/message.js      entrypoint, called with each Message
  lib/reply.js             findReply / sendReply (pure, gets `api` injected)
  lib/config.js            GENERATED and gitignored (contains passkeys)
tests/test_bot.py          unittest: bot.py
tests/test_build_serverless.py  unittest: build script
tests/reply.test.mjs       node:test: tgcloud/lib/reply.js
package.json               npm scripts and the @tgcloud/cli dev dependency
```

## Config (.env)

- `PASSKEY_<n>` pairs with `RESPONSE_<n>` and/or `FILE_<n>`, plus an optional `FILE_TYPE_<n>`. Each passkey needs at least a response or a file. Duplicate passkey values are an error.
- `INVALID_RESPONSE`, `INVALID_FILE`, `INVALID_FILE_TYPE` are optional. The default reply is `Invalid passkey ❌`.
- `FILE_<n>` can be a URL, a local path (relative to the repo root), or a Telegram `file_id`.
- The file type is guessed from the extension (see `EXTENSION_TYPES` in `bot.py`). Anything unrecognised is sent as a `document`. `file_id`s have no extension, so they need `FILE_TYPE_<n>`.
- Text longer than 1024 characters (`CAPTION_LIMIT`) can't be a caption. The bot sends the file first and then the text as its own message.
- `UPLOAD_CHAT_ID` is used only by the serverless build (see below).
- `.env` parsing is in `load_env_file`. Real environment variables override `.env`, and `\n` inside double quotes becomes a newline.

## Telegram Serverless

Docs: https://core.telegram.org/bots/serverless

Runtime limits that shape this code:

- Only JavaScript ES modules, run in a V8 isolate. No npm packages, no filesystem, no environment variables.
- The only imports allowed are `sdk` (`api`, `db`, `fetch`, `InputFile`, `BotApiError`) and modules inside `tgcloud/`.
- Relative imports must end in `.js` and must not leave `tgcloud/`.
- `handlers/` is flat, with one file per update type. A file's default export is called as `(payload, ctx)`.
- `api.<method>(params)` returns the unwrapped `result`. It throws `BotApiError` when the response is `ok: false`.

### Build step

Serverless can't read `.env` or local files, so `build_serverless.py`:

1. Parses `.env` with the loaders in `bot.py`, which also validate it.
2. Resolves each reply's file type.
3. Uploads local files with `UPLOAD_CHAT_ID` and keeps the returned `file_id`. It then deletes the upload message. `file_id`s are tied to the bot, so the cache in `.tgcloud-files.json` is keyed by bot id, then by path, size, mtime and type. Unchanged files aren't uploaded again.
4. Writes `tgcloud/lib/config.js` as `export default { responses: { [passkey]: {text?, file?, type?} }, invalid: {...} }`. JSON is valid JS.

Rebuild and redeploy after every `.env` change: `npm run deploy`.

### Conventions

- Keep `tgcloud/lib/reply.js` free of `sdk` imports. It receives `api` as an argument so `npm test` can run it in plain Node with a fake.
- Never commit `tgcloud/lib/config.js`, `.tgcloud/`, `.tgcloud-files.json` or `.env`. All of them are gitignored.
- Self-hosted and serverless behaviour should match. A change to reply logic in `bot.py` should be made in `tgcloud/lib/reply.js` too, with tests on both sides.
- No database is used yet. If one is added, define tables in `tgcloud/schema.js` (no foreign keys), and deploy with `npx tgcloud push` followed by `npx tgcloud migrate`.

## Commands

```bash
python -m unittest discover tests      # Python tests
npm test                               # JS handler logic tests
npm run build                          # .env -> tgcloud/lib/config.js
npm run deploy                         # build + tgcloud push
npx tgcloud run handlers/message '{ chat: { id: 123 }, text: "passkey" }'   # run on platform without deploying
npx tgcloud webhook                    # inspect the managed webhook
```

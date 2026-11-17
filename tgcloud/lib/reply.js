// Passkey matching and reply sending. Mirrors TelegramPasskeyBot in bot.py.
// Takes the Bot API client as an argument (no 'sdk' import) so it can be
// tested locally with plain Node: `npm test`.

export const CAPTION_LIMIT = 1024; // Telegram's max caption length for media

// file type -> [Bot API method, file parameter name]
export const FILE_TYPES = {
  photo: ['sendPhoto', 'photo'],
  animation: ['sendAnimation', 'animation'],
  video: ['sendVideo', 'video'],
  audio: ['sendAudio', 'audio'],
  voice: ['sendVoice', 'voice'],
  document: ['sendDocument', 'document'],
};

export const VENUE_VIDEO_CALLBACK = 'venue_video';
export const VENUE_VIDEO_BUTTON = '🎬 Video guide to get to venue';
export const WEBSITE_BUTTON = '🌐 Visit the website';

// config.launch: { unlockAt: epoch ms, locked, welcome, venueVideo, websiteUrl } | undefined
export function isLocked(config, now = Date.now()) {
  return Boolean(config.launch) && now < config.launch.unlockAt;
}

// True for /start, /start <payload> and /start@BotName.
export function isStartCommand(text) {
  const command = text.trim().split(/\s+/, 1)[0] ?? '';
  return command.split('@', 1)[0] === '/start';
}

export function welcomeMarkup(launch) {
  const rows = [];
  if (launch.venueVideo) {
    rows.push([{ text: VENUE_VIDEO_BUTTON, callback_data: VENUE_VIDEO_CALLBACK }]);
  }
  if (launch.websiteUrl) rows.push([{ text: WEBSITE_BUTTON, url: launch.websiteUrl }]);
  return rows.length ? { inline_keyboard: rows } : undefined;
}

// Returns the reply for a message text, or null if the message has no text.
export function findReply(config, text, now = Date.now()) {
  if (typeof text !== 'string') return null;
  const key = text.trim();
  if (Object.prototype.hasOwnProperty.call(config.responses, key)) return config.responses[key];
  return isLocked(config, now) ? config.launch.locked : config.invalid;
}

// reply: { text?: string, file?: string (URL or file_id), type?: keyof FILE_TYPES }
export async function sendReply(api, chatId, reply) {
  if (!reply.file) {
    if (reply.text) await api.sendMessage({ chat_id: chatId, text: reply.text });
    return;
  }

  const [method, field] = FILE_TYPES[reply.type] ?? FILE_TYPES.document;
  const params = { chat_id: chatId, [field]: reply.file };

  if (reply.text && reply.text.length > CAPTION_LIMIT) {
    // Too long for a caption: send the file, then the text separately.
    await api[method](params);
    await api.sendMessage({ chat_id: chatId, text: reply.text });
  } else {
    if (reply.text) params.caption = reply.text;
    await api[method](params);
  }
}

export async function handleMessage(api, config, message, now = Date.now()) {
  const chatId = message.chat?.id;
  if (typeof message.text !== 'string' || chatId === undefined) return; // stickers, photos, etc.

  if (isLocked(config, now) && isStartCommand(message.text)) {
    const params = { chat_id: chatId, text: config.launch.welcome };
    const markup = welcomeMarkup(config.launch);
    if (markup) params.reply_markup = markup;
    await api.sendMessage(params);
    return;
  }

  await sendReply(api, chatId, findReply(config, message.text, now));
}

export async function handleCallbackQuery(api, config, query) {
  await api.answerCallbackQuery({ callback_query_id: query.id }); // stops the button's spinner

  const chatId = query.message?.chat?.id;
  if (chatId === undefined) return;
  if (query.data === VENUE_VIDEO_CALLBACK && config.launch?.venueVideo) {
    await sendReply(api, chatId, config.launch.venueVideo);
  }
}

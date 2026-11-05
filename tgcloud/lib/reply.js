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

// Returns the reply for a message text, or null if the message has no text.
export function findReply(config, text) {
  if (typeof text !== 'string') return null;
  const key = text.trim();
  return Object.prototype.hasOwnProperty.call(config.responses, key)
    ? config.responses[key]
    : config.invalid;
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

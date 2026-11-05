import { api } from 'sdk';
import config from '../lib/config.js';
import { findReply, sendReply } from '../lib/reply.js';

// Called by Telegram Serverless for every incoming `message` update.
export default async function (message) {
  const reply = findReply(config, message.text);
  if (!reply) return; // stickers, photos, etc.
  await sendReply(api, message.chat.id, reply);
}

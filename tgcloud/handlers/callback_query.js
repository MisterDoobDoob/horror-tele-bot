import { api } from 'sdk';
import config from '../lib/config.js';
import { handleCallbackQuery } from '../lib/reply.js';

// Called by Telegram Serverless when an inline button (e.g. the venue video) is tapped.
export default async function (query) {
  await handleCallbackQuery(api, config, query);
}

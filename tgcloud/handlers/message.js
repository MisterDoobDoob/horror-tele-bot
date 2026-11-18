import { api } from 'sdk';
import config from '../lib/config.js';
import { handleMessage } from '../lib/reply.js';

// Called by Telegram Serverless for every incoming `message` update.
export default async function (message) {
  await handleMessage(api, config, message);
}

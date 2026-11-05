import { test } from 'node:test';
import assert from 'node:assert/strict';
import { CAPTION_LIMIT, findReply, sendReply } from '../tgcloud/lib/reply.js';

function fakeApi() {
  const calls = [];
  const handler = { get: (_, method) => async (params) => { calls.push([method, params]); } };
  return { api: new Proxy({}, handler), calls };
}

const config = {
  responses: { alpha: { text: 'A' }, beta: { text: 'B', file: 'https://x/b.jpg', type: 'photo' } },
  invalid: { text: 'nope' },
};

test('matches trimmed passkey', () => {
  assert.deepEqual(findReply(config, '  alpha \n'), { text: 'A' });
});

test('falls back to invalid reply', () => {
  assert.deepEqual(findReply(config, 'wrong'), { text: 'nope' });
  assert.deepEqual(findReply(config, 'toString'), { text: 'nope' }); // no prototype leaks
});

test('ignores messages without text', () => {
  assert.equal(findReply(config, undefined), null);
});

test('sends text-only reply', async () => {
  const { api, calls } = fakeApi();
  await sendReply(api, 1, { text: 'hi' });
  assert.deepEqual(calls, [['sendMessage', { chat_id: 1, text: 'hi' }]]);
});

test('sends file with caption', async () => {
  const { api, calls } = fakeApi();
  await sendReply(api, 1, config.responses.beta);
  assert.deepEqual(calls, [['sendPhoto', { chat_id: 1, photo: 'https://x/b.jpg', caption: 'B' }]]);
});

test('unknown type is sent as document', async () => {
  const { api, calls } = fakeApi();
  await sendReply(api, 1, { file: 'FILEID' });
  assert.deepEqual(calls, [['sendDocument', { chat_id: 1, document: 'FILEID' }]]);
});

test('long text is sent after the file', async () => {
  const { api, calls } = fakeApi();
  const text = 'x'.repeat(CAPTION_LIMIT + 1);
  await sendReply(api, 1, { text, file: 'v.mp4', type: 'video' });
  assert.deepEqual(calls, [
    ['sendVideo', { chat_id: 1, video: 'v.mp4' }],
    ['sendMessage', { chat_id: 1, text }],
  ]);
});

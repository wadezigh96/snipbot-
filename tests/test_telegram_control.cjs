"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const {
  STATE_KEY,
  HEARTBEAT_KEY,
  safeEqual,
  isAuthorizedUpdate,
  parseCommand,
  validateUpdate,
  handleTelegramUpdate,
} = require("../api/_lib/telegram-control");
const { createHandler } = require("../api/telegram-webhook");

const env = {
  TELEGRAM_OWNER_USER_ID: "12345",
  TELEGRAM_OWNER_CHAT_ID: "12345",
  TELEGRAM_WEBHOOK_SECRET: "secret-test-value",
  TELEGRAM_BOT_TOKEN: "test-token",
  CONTROL_STORE_URL: "https://store.example.test",
  CONTROL_STORE_TOKEN: "store-test-token",
};

function update(id, text, fromId = 12345, chatId = 12345, chatType = "private") {
  return {
    update_id: id,
    message: {
      text,
      from: { id: fromId },
      chat: { id: chatId, type: chatType },
    },
  };
}

function memoryStore(initial = {}) {
  const data = new Map(Object.entries(initial));
  return {
    data,
    async get(key) { return data.has(key) ? data.get(key) : null; },
    async set(key, value, options = {}) {
      if (options.nx && data.has(key)) return null;
      data.set(key, String(value));
      return "OK";
    },
  };
}

function responseStub() {
  return {
    headers: {},
    setHeader(k, v) { this.headers[k] = v; },
    end(body) { this.body = body; },
  };
}

test("constant-time secret comparison rejects empty/mismatched values", () => {
  assert.equal(safeEqual("same", "same"), true);
  assert.equal(safeEqual("same", "diff"), false);
  assert.equal(safeEqual("", ""), false);
});

test("only exact owner user and private chat are authorized", () => {
  assert.equal(isAuthorizedUpdate(update(1, "/status"), env), true);
  assert.equal(isAuthorizedUpdate(update(2, "/pause", 999), env), false);
  assert.equal(isAuthorizedUpdate(update(3, "/pause", 12345, 999), env), false);
  assert.equal(isAuthorizedUpdate(update(4, "/pause", 12345, 12345, "group"), env), false);
});

test("only status, pause and resume commands parse", () => {
  assert.equal(parseCommand("/status"), "status");
  assert.equal(parseCommand("/pause@my_bot"), "pause");
  assert.equal(parseCommand("/resume"), "resume");
  assert.equal(parseCommand("/buy"), null);
  assert.equal(parseCommand("/pause now"), null);
  assert.equal(parseCommand("pause"), null);
});

test("update validation rejects malformed and oversized updates", () => {
  assert.equal(validateUpdate(update(1, "/status")), true);
  assert.equal(validateUpdate({ update_id: -1 }), false);
  assert.equal(validateUpdate(null), false);
  assert.equal(validateUpdate({ update_id: 1, huge: "x".repeat(33 * 1024) }), false);
});

test("missing state defaults to paused and status never implies trading", async () => {
  const store = memoryStore();
  let sent;
  const result = await handleTelegramUpdate(update(10, "/status"), env, store, async (chat, message) => { sent = { chat, message }; });
  assert.equal(result.status, "processed");
  assert.match(sent.message, /Monitoring: PAUSED/);
  assert.match(sent.message, /Execution: DISABLED/);
});

test("pause and resume only change monitoring state", async () => {
  const store = memoryStore();
  await handleTelegramUpdate(update(11, "/resume"), env, store, async () => {});
  assert.equal(await store.get(STATE_KEY), "running");
  await handleTelegramUpdate(update(12, "/pause"), env, store, async () => {});
  assert.equal(await store.get(STATE_KEY), "paused");
});

test("unauthorized and unknown commands do not mutate state or reply", async () => {
  const store = memoryStore();
  let replies = 0;
  const send = async () => { replies++; };
  assert.equal((await handleTelegramUpdate(update(13, "/resume", 777), env, store, send)).status, "ignored");
  assert.equal((await handleTelegramUpdate(update(14, "/buy"), env, store, send)).status, "ignored");
  assert.equal(await store.get(STATE_KEY), null);
  assert.equal(replies, 0);
});

test("duplicate update is idempotently ignored", async () => {
  const store = memoryStore();
  let replies = 0;
  const send = async () => { replies++; };
  await handleTelegramUpdate(update(15, "/pause"), env, store, send);
  const second = await handleTelegramUpdate(update(15, "/resume"), env, store, send);
  assert.equal(second.status, "duplicate");
  assert.equal(await store.get(STATE_KEY), "paused");
  assert.equal(replies, 1);
});

test("status includes worker heartbeat only when a valid timestamp exists", async () => {
  const store = memoryStore({ [HEARTBEAT_KEY]: String(Math.floor(Date.now() / 1000)) });
  let message = "";
  await handleTelegramUpdate(update(16, "/status"), env, store, async (_chat, value) => { message = value; });
  assert.match(message, /Worker heartbeat: 0s ago/);
});

test("webhook rejects GET and invalid webhook secret before touching the store", async () => {
  let storeCalls = 0;
  const handler = createHandler({ env, storeFactory: () => { storeCalls++; return memoryStore(); }, sendReply: async () => {} });
  const getRes = responseStub();
  await handler({ method: "GET", headers: {}, body: {} }, getRes);
  assert.equal(getRes.statusCode, 405);
  const badRes = responseStub();
  await handler({ method: "POST", headers: { "x-telegram-bot-api-secret-token": "wrong" }, body: update(17, "/pause") }, badRes);
  assert.equal(badRes.statusCode, 401);
  assert.equal(storeCalls, 0);
});

test("webhook uses generic 503 on store failure without leaking exception details", async () => {
  const handler = createHandler({ env, storeFactory: () => ({ get: async () => { throw new Error("sensitive provider detail"); } }) });
  const res = responseStub();
  await handler({ method: "POST", headers: { "x-telegram-bot-api-secret-token": env.TELEGRAM_WEBHOOK_SECRET }, body: update(18, "/status") }, res);
  assert.equal(res.statusCode, 503);
  assert.doesNotMatch(res.body, /sensitive provider detail|store-test-token|secret-test-value/);
});

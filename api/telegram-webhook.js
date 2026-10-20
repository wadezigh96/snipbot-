"use strict";

const { safeEqual, createRedisStore, handleTelegramUpdate } = require("../lib/telegram-control");

function sendJson(res, statusCode, payload) {
  res.statusCode = statusCode;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.end(JSON.stringify(payload));
}

async function sendTelegramReply(chatId, text, env, fetchImpl = fetch) {
  const token = String(env.TELEGRAM_BOT_TOKEN || "").trim();
  if (!token) throw new Error("telegram_not_configured");
  const response = await fetchImpl(`https://api.telegram.org/bot${token}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      chat_id: chatId,
      text: String(text).slice(0, 3000),
      disable_web_page_preview: true,
    }),
    signal: AbortSignal.timeout(5000),
  });
  if (!response.ok) throw new Error("telegram_reply_failed");
  const payload = await response.json();
  if (!payload || payload.ok !== true) throw new Error("telegram_reply_failed");
}

function createHandler(deps = {}) {
  const env = deps.env || process.env;
  const fetchImpl = deps.fetchImpl || fetch;
  const storeFactory = deps.storeFactory || ((e) => createRedisStore(e, fetchImpl));
  const reply = deps.sendReply || ((chatId, message) => sendTelegramReply(chatId, message, env, fetchImpl));

  return async function telegramWebhook(req, res) {
    if (req.method !== "POST") {
      res.setHeader("Allow", "POST");
      return sendJson(res, 405, { ok: false, error: "method_not_allowed" });
    }

    const expectedSecret = String(env.TELEGRAM_WEBHOOK_SECRET || "").trim();
    const providedSecret = req.headers && req.headers["x-telegram-bot-api-secret-token"];
    if (!expectedSecret || !safeEqual(expectedSecret, typeof providedSecret === "string" ? providedSecret : "")) {
      return sendJson(res, 401, { ok: false, error: "unauthorized" });
    }

    const update = req.body;
    if (!update || typeof update !== "object" || Array.isArray(update)) {
      return sendJson(res, 400, { ok: false, error: "invalid_request" });
    }

    try {
      const store = storeFactory(env);
      const result = await handleTelegramUpdate(update, env, store, reply);
      if (result.status === "invalid_update") return sendJson(res, 400, { ok: false, error: "invalid_request" });
      return sendJson(res, 200, { ok: true, status: result.status });
    } catch {
      // Do not log provider exceptions, tokens, URLs, or raw request payloads.
      return sendJson(res, 503, { ok: false, error: "temporarily_unavailable" });
    }
  };
}

module.exports = createHandler();
module.exports.createHandler = createHandler;

"use strict";

const crypto = require("node:crypto");

const STATE_KEY = "pumpfun:control:monitor_state";
const HEARTBEAT_KEY = "pumpfun:control:worker_heartbeat";
const UPDATE_PREFIX = "pumpfun:control:telegram_update:";

function safeEqual(left, right) {
  if (typeof left !== "string" || typeof right !== "string" || !left || !right) return false;
  const a = Buffer.from(left, "utf8");
  const b = Buffer.from(right, "utf8");
  return a.length === b.length && crypto.timingSafeEqual(a, b);
}

function isAuthorizedUpdate(update, env) {
  const message = update && update.message;
  if (!message || !message.from || !message.chat || message.chat.type !== "private") return false;
  const owner = String(env.TELEGRAM_OWNER_USER_ID || "").trim();
  const expectedChat = String(env.TELEGRAM_OWNER_CHAT_ID || "").trim();
  return Boolean(owner && expectedChat) &&
    String(message.from.id) === owner &&
    String(message.chat.id) === expectedChat;
}

function parseCommand(text) {
  if (typeof text !== "string") return null;
  const match = /^\/(status|pause|resume)(?:@[A-Za-z0-9_]+)?$/i.exec(text.trim());
  return match ? match[1].toLowerCase() : null;
}

function validateUpdate(update) {
  if (!update || typeof update !== "object" || Array.isArray(update)) return false;
  if (!Number.isSafeInteger(update.update_id) || update.update_id < 0) return false;
  try {
    return Buffer.byteLength(JSON.stringify(update), "utf8") <= 32 * 1024;
  } catch {
    return false;
  }
}

async function redisCommand(env, command, fetchImpl = fetch) {
  const url = String(env.CONTROL_STORE_URL || "").trim();
  const token = String(env.CONTROL_STORE_TOKEN || "").trim();
  if (!url || !token) throw new Error("control_store_unconfigured");
  let parsed;
  try { parsed = new URL(url); } catch { throw new Error("control_store_unconfigured"); }
  if (parsed.protocol !== "https:") throw new Error("control_store_unconfigured");
  const response = await fetchImpl(parsed.toString(), {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify(command),
    signal: AbortSignal.timeout(4000),
  });
  if (!response.ok) throw new Error("control_store_unavailable");
  const payload = await response.json();
  if (!payload || payload.error) throw new Error("control_store_unavailable");
  return payload.result;
}

function createRedisStore(env, fetchImpl = fetch) {
  return {
    async get(key) {
      const value = await redisCommand(env, ["GET", key], fetchImpl);
      return value == null ? null : String(value);
    },
    async set(key, value, options = {}) {
      const command = ["SET", key, String(value)];
      if (options.nx) command.push("NX");
      if (options.exSeconds) command.push("EX", String(options.exSeconds));
      return redisCommand(env, command, fetchImpl);
    },
  };
}

async function handleTelegramUpdate(update, env, store, sendReply) {
  if (!validateUpdate(update)) return { status: "invalid_update" };
  if (!isAuthorizedUpdate(update, env)) return { status: "ignored" };
  const message = update.message;
  const command = parseCommand(message.text);
  if (!command) return { status: "ignored" };
  const updateKey = UPDATE_PREFIX + String(update.update_id);
  if (await store.get(updateKey)) return { status: "duplicate" };

  let reply;
  if (command === "pause" || command === "resume") {
    const state = command === "pause" ? "paused" : "running";
    if (await store.set(STATE_KEY, state) !== "OK") throw new Error("control_store_write_failed");
    reply = state === "paused"
      ? "PumpFun FOMO Radar: monitoring PAUSED. Trading remains DISABLED."
      : "PumpFun FOMO Radar: monitoring RESUMED. Monitoring only; trading remains DISABLED.";
  } else {
    const state = (await store.get(STATE_KEY)) || "paused";
    const heartbeat = await store.get(HEARTBEAT_KEY);
    let heartbeatText = "unavailable";
    if (heartbeat) {
      const timestamp = Number(heartbeat);
      if (Number.isFinite(timestamp) && timestamp > 0) {
        const age = Math.max(0, Math.floor(Date.now() / 1000 - timestamp));
        heartbeatText = age < 60 ? `${age}s ago` : `${Math.floor(age / 60)}m ago`;
      }
    }
    reply = `PumpFun FOMO Radar status\nMonitoring: ${state.toUpperCase()}\nWorker heartbeat: ${heartbeatText}\nExecution: DISABLED`;
  }
  await sendReply(String(message.chat.id), reply);
  const marker = await store.set(updateKey, "1", { nx: true, exSeconds: 86400 });
  return { status: marker === "OK" ? "processed" : "duplicate" };
}

module.exports = { STATE_KEY, HEARTBEAT_KEY, safeEqual, isAuthorizedUpdate, parseCommand, validateUpdate, createRedisStore, handleTelegramUpdate };

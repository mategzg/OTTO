"use strict";

const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const { execFile } = require("node:child_process");

const MARKER_REL = path.join(".openclaw", "CANONICAL_ROOT.json");
const HOOK_BACKLOG_POLICY = path.join("state", "hook_backlog_policy.json");
const HOOK_BACKLOG_DIR = path.join("state", "hook_backlog");

function isObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function utcNowIso() {
  return new Date().toISOString();
}

function utcStamp() {
  return utcNowIso().replace(/[-:.]/g, "").replace("T", "T").replace("Z", "Z");
}

function normalizeAction(event) {
  const type = String(event?.type || "").toLowerCase();
  const action = String(event?.action || "").toLowerCase();
  if (type === "message:received") return "received";
  if (type === "message:sent") return "sent";
  if (type === "message" && (action === "received" || action === "sent")) return action;
  return "";
}

function findCanonicalRoot(startDir) {
  let current = path.resolve(startDir || process.cwd());
  for (;;) {
    const marker = path.join(current, MARKER_REL);
    if (fs.existsSync(marker) && fs.statSync(marker).isFile()) return current;
    const parent = path.dirname(current);
    if (parent === current) return "";
    current = parent;
  }
}

function resolveWorkspaceDir(event) {
  const context = isObject(event?.context) ? event.context : {};
  const workspaceDir = String(context.workspaceDir || "").trim();
  if (workspaceDir) return workspaceDir;
  return process.cwd();
}

function compactContext(context, eventTimestamp) {
  const metadata = isObject(context.metadata) ? context.metadata : {};
  return {
    workspaceDir: String(context.workspaceDir || "").trim(),
    channelId: String(context.channelId || "").trim(),
    accountId: String(context.accountId || "").trim(),
    conversationId: String(context.conversationId || "").trim(),
    messageId: String(context.messageId || "").trim(),
    timestamp: String(context.timestamp || eventTimestamp || "").trim(),
    from: isObject(context.from) ? context.from : {},
    to: isObject(context.to) ? context.to : {},
    content: typeof context.content === "string" ? context.content : "",
    metadata: {
      threadId: String(metadata.threadId || "").trim(),
      senderId: String(metadata.senderId || "").trim(),
      senderName: String(metadata.senderName || "").trim(),
      senderUsername: String(metadata.senderUsername || "").trim(),
      senderE164: String(metadata.senderE164 || "").trim(),
      channelName: String(metadata.channelName || context.channelName || "").trim(),
    },
    attachments: Array.isArray(context.attachments) ? context.attachments : [],
  };
}

function buildIngressPayload(event, workspaceDir, action) {
  const context = isObject(event?.context) ? event.context : {};
  return {
    type: "message",
    action,
    timestamp: String(event?.timestamp || "").trim(),
    sessionKey: String(event?.sessionKey || "").trim(),
    context: compactContext(
      {
        ...context,
        workspaceDir,
      },
      event?.timestamp
    ),
  };
}

function loadBacklogPolicy(workspaceRoot) {
  const defaults = {
    max_content_preview_chars: 64,
    max_bytes_per_backlog_file: 10_000_000,
  };
  const policyPath = path.join(workspaceRoot, HOOK_BACKLOG_POLICY);
  try {
    if (!fs.existsSync(policyPath)) return defaults;
    const raw = fs.readFileSync(policyPath, "utf8");
    const parsed = JSON.parse(raw);
    if (!isObject(parsed)) return defaults;
    return {
      ...defaults,
      ...parsed,
    };
  } catch (_error) {
    return defaults;
  }
}

function hashHex(algo, value) {
  return crypto.createHash(algo).update(String(value || ""), "utf8").digest("hex");
}

function safePreview(text, maxChars) {
  const n = Number.isFinite(maxChars) ? Math.max(0, Math.floor(maxChars)) : 0;
  if (!n) return "";
  const compact = String(text || "").trim().replace(/\s+/g, " ");
  if (compact.length <= n) return compact;
  return `${compact.slice(0, Math.max(1, n - 1))}…`;
}

function rotateBacklogIfNeeded(eventsPath, maxBytes) {
  try {
    if (!fs.existsSync(eventsPath)) return;
    const stat = fs.statSync(eventsPath);
    if (!stat.isFile()) return;
    if (stat.size < maxBytes) return;
    const rotated = eventsPath.replace(/events\.ndjson$/, `events_${utcStamp()}.ndjson`);
    fs.renameSync(eventsPath, rotated);
  } catch (_error) {
    // fail-open: never throw into gateway path
  }
}

function appendHookBacklog(workspaceRoot, payload) {
  try {
    const policy = loadBacklogPolicy(workspaceRoot);
    const context = isObject(payload?.context) ? payload.context : {};
    const metadata = isObject(context.metadata) ? context.metadata : {};
    const content = typeof context.content === "string" ? context.content : "";
    const contentHash = hashHex("sha256", content);
    const payloadHash = hashHex("sha256", JSON.stringify(payload || {}));
    const seed = [
      String(payload?.action || ""),
      String(context.channelId || ""),
      String(context.accountId || ""),
      String(context.conversationId || ""),
      String(metadata.threadId || ""),
      String(context.messageId || ""),
      String(payload?.timestamp || ""),
      String(payload?.sessionKey || ""),
      contentHash,
    ].join("|");
    const eventId = `hkb_${hashHex("sha1", seed).slice(0, 16)}`;
    const backlogDir = path.join(workspaceRoot, HOOK_BACKLOG_DIR);
    const payloadDir = path.join(backlogDir, "payloads");
    fs.mkdirSync(payloadDir, { recursive: true });

    const payloadRelpath = path.join("state", "hook_backlog", "payloads", `${eventId}.json`);
    const payloadPath = path.join(workspaceRoot, payloadRelpath);
    if (!fs.existsSync(payloadPath)) {
      fs.writeFileSync(payloadPath, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
    }

    const maxBytes = Math.max(10_000, Number(policy.max_bytes_per_backlog_file || 10_000_000));
    const eventsPath = path.join(backlogDir, "events.ndjson");
    rotateBacklogIfNeeded(eventsPath, maxBytes);

    const attachments = Array.isArray(context.attachments) ? context.attachments : [];
    const record = {
      event_id: eventId,
      created_at: utcNowIso(),
      source: "workspace_hook",
      event_type: "message",
      action: String(payload?.action || ""),
      channel: String(context.channelId || ""),
      account_id: String(context.accountId || ""),
      conversation_id: String(context.conversationId || ""),
      channel_id: String(context.channelId || ""),
      thread_id: String(metadata.threadId || ""),
      session_key: String(payload?.sessionKey || ""),
      message_id: String(context.messageId || ""),
      timestamp: String(payload?.timestamp || ""),
      content_hash: contentHash,
      content_preview: safePreview(content, Number(policy.max_content_preview_chars || 0)),
      attachments_meta: attachments
        .filter((x) => isObject(x))
        .map((x) => ({
          name: String(x.name || "").slice(0, 120),
          path: String(x.path || "").slice(0, 260),
          url: String(x.url || "").slice(0, 260),
        })),
      workspace_dir_hint: String(context.workspaceDir || ""),
      raw_context_hash: hashHex("sha256", JSON.stringify(context)),
      payload_hash: payloadHash,
      payload_relpath: payloadRelpath.replace(/\\/g, "/"),
      version: 1,
    };
    fs.appendFileSync(eventsPath, `${JSON.stringify(record)}\n`, "utf8");
    return { ok: true, eventId };
  } catch (error) {
    return { ok: false, reason: String(error && error.message ? error.message : error) };
  }
}

function runIngress(workspaceRoot, payload) {
  const script = path.join(workspaceRoot, "scripts", "channel_ingress_adapter.py");
  if (!fs.existsSync(script)) {
    console.warn("[otto-runtime-bridge] missing adapter script:", script);
    return;
  }
  const args = ["--root", workspaceRoot, "--event-json", JSON.stringify(payload)];
  execFile(
    "python3",
    [script, ...args],
    { timeout: 250, windowsHide: true, maxBuffer: 128 * 1024 },
    (error, stdout, stderr) => {
      if (error) {
        console.warn("[otto-runtime-bridge] fast-path failed:", String(error.message || error));
        return;
      }
      if (stderr && String(stderr).trim()) {
        console.warn("[otto-runtime-bridge] fast-path stderr:", String(stderr).trim().slice(0, 400));
      }
    }
  );
}

async function handler(event) {
  try {
    const action = normalizeAction(event);
    if (!action) return;
    const workspaceHint = resolveWorkspaceDir(event);
    const canonicalRoot = findCanonicalRoot(workspaceHint);
    if (!canonicalRoot) {
      console.warn("[otto-runtime-bridge] missing canonical root marker; skipping event");
      return;
    }
    const payload = buildIngressPayload(event, canonicalRoot, action);
    const backlog = appendHookBacklog(canonicalRoot, payload);
    if (!backlog.ok) {
      console.warn("[otto-runtime-bridge] backlog append failed:", backlog.reason);
    }
    runIngress(canonicalRoot, payload);
  } catch (error) {
    console.warn("[otto-runtime-bridge] unexpected error:", String(error && error.message ? error.message : error));
  }
}

module.exports = handler;
module.exports.default = handler;

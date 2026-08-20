const HEADERS = [
  "ID", "الموضوع", "تاريخ النشر", "ساعة النشر", "نوع الجدولة", "الحالة",
  "المحتوى", "وصف الصورة", "رابط الصورة", "Facebook Status", "LinkedIn Status",
  "Facebook Post ID", "LinkedIn Post ID", "Facebook Comment Status", "Facebook Comment ID",
  "Facebook Like Status", "LinkedIn Image ID", "آخر خطأ", "وقت آخر تشغيل",
  "المصادر القانونية", "ملاحظات",
];

function b64urlBytes(bytes) {
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  return btoa(binary).replace(/=/g, "").replace(/\+/g, "-").replace(/\//g, "_");
}

function b64urlText(value) {
  return b64urlBytes(new TextEncoder().encode(value));
}

function pemToBytes(pem) {
  const body = pem.replace(/-----BEGIN PRIVATE KEY-----/g, "").replace(/-----END PRIVATE KEY-----/g, "").replace(/\s+/g, "");
  const raw = atob(body);
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}

async function googleAccessToken(env) {
  const info = JSON.parse(env.GOOGLE_SERVICE_ACCOUNT_JSON);
  const now = Math.floor(Date.now() / 1000);
  const header = b64urlText(JSON.stringify({ alg: "RS256", typ: "JWT" }));
  const claim = b64urlText(JSON.stringify({
    iss: info.client_email,
    scope: "https://www.googleapis.com/auth/spreadsheets",
    aud: "https://oauth2.googleapis.com/token",
    iat: now,
    exp: now + 3600,
  }));
  const unsigned = `${header}.${claim}`;
  const key = await crypto.subtle.importKey(
    "pkcs8",
    pemToBytes(info.private_key),
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const signature = await crypto.subtle.sign("RSASSA-PKCS1-v1_5", key, new TextEncoder().encode(unsigned));
  const assertion = `${unsigned}.${b64urlBytes(new Uint8Array(signature))}`;
  const response = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ grant_type: "urn:ietf:params:oauth:grant-type:jwt-bearer", assertion }),
  });
  const data = await response.json();
  if (!response.ok || !data.access_token) throw new Error(`Google token exchange failed: ${JSON.stringify(data)}`);
  return data.access_token;
}

async function sheetValues(env, range = "A:U") {
  const token = await googleAccessToken(env);
  const sheetName = env.GOOGLE_SHEET_NAME || "Content";
  const encoded = encodeURIComponent(`${sheetName}!${range}`);
  const response = await fetch(`https://sheets.googleapis.com/v4/spreadsheets/${encodeURIComponent(env.GOOGLE_SHEET_ID)}/values/${encoded}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const data = await response.json();
  if (!response.ok) throw new Error(`Google Sheets read failed: ${JSON.stringify(data)}`);
  return data.values || [];
}

function rowToDict(row) {
  const padded = [...row, ...Array(Math.max(0, HEADERS.length - row.length)).fill("")];
  return Object.fromEntries(HEADERS.map((h, i) => [h, padded[i] || ""]));
}

async function updateSheetRow(env, rowNumber, patch) {
  const token = await googleAccessToken(env);
  const sheetName = env.GOOGLE_SHEET_NAME || "Content";
  const encoded = encodeURIComponent(`${sheetName}!A${rowNumber}:U${rowNumber}`);
  const read = await fetch(`https://sheets.googleapis.com/v4/spreadsheets/${encodeURIComponent(env.GOOGLE_SHEET_ID)}/values/${encoded}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const readData = await read.json();
  if (!read.ok) throw new Error(`Google Sheets row read failed: ${JSON.stringify(readData)}`);
  const existing = (readData.values?.[0] || []).slice();
  while (existing.length < HEADERS.length) existing.push("");
  for (const [key, value] of Object.entries(patch)) {
    const index = HEADERS.indexOf(key);
    if (index >= 0) existing[index] = value == null ? "" : String(value);
  }
  const response = await fetch(`https://sheets.googleapis.com/v4/spreadsheets/${encodeURIComponent(env.GOOGLE_SHEET_ID)}/values/${encoded}?valueInputOption=RAW`, {
    method: "PUT",
    headers: { Authorization: `Bearer ${token}`, "content-type": "application/json" },
    body: JSON.stringify({ range: `${sheetName}!A${rowNumber}:U${rowNumber}`, majorDimension: "ROWS", values: [existing] }),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(`Google Sheets row update failed: ${JSON.stringify(data)}`);
}

async function telegram(env, method, payload) {
  const response = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/${method}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok || !data.ok) throw new Error(`Telegram ${method} failed: ${JSON.stringify(data)}`);
  return data.result;
}

async function send(env, text, replyMarkup) {
  return telegram(env, "sendMessage", {
    chat_id: env.TELEGRAM_CHAT_ID,
    text,
    disable_web_page_preview: true,
    ...(replyMarkup ? { reply_markup: replyMarkup } : {}),
  });
}

function cairoParts(date = new Date()) {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Africa/Cairo", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hour12: false,
  }).formatToParts(date);
  return Object.fromEntries(parts.filter((p) => p.type !== "literal").map((p) => [p.type, p.value]));
}

function dateKey(parts) { return `${parts.year}-${parts.month}-${parts.day}`; }

async function statusText(env) {
  const values = await sheetValues(env);
  const rows = values.slice(1).map(rowToDict);
  const today = cairoParts();
  const todayKey = dateKey(today);
  const counts = { total: 0, published: 0, pending: 0, review: 0, failed: 0 };
  let next = null;
  for (const row of rows) {
    const status = String(row["الحالة"] || "").trim().toUpperCase();
    const d = String(row["تاريخ النشر"] || "").trim();
    const t = String(row["ساعة النشر"] || "").trim();
    if (d === todayKey || d.includes(`${today.day}/${today.month}`)) counts.total++;
    if (["PUBLISHED", "READY_FOR_SOCIAL_PUBLISH", "PUBLISHED_PARTIAL"].includes(status)) counts.published++;
    if (["READY", "PENDING", "APPROVED", "SCHEDULED"].includes(status)) counts.pending++;
    if (["NEEDS_REVIEW", "PENDING_REVIEW", "REVIEW"].includes(status)) counts.review++;
    if (status.includes("FAIL") || status === "ERROR") counts.failed++;
    if (d === todayKey && t && (!next || t < next)) next = t;
  }
  return [
    "🟢 Khyrat Legal Content Engine",
    "",
    `📅 اليوم: ${todayKey}`,
    `📌 منشورات اليوم: ${counts.total}`,
    `✅ منشورات ناجحة: ${counts.published}`,
    `⏳ منتظرة: ${counts.pending}`,
    `🟡 مراجعة: ${counts.review}`,
    `🔴 فشل: ${counts.failed}`,
    `📘 إجمالي Post Bank/Content: ${rows.length}`,
    `🕐 الوقت الحالي: ${today.hour}:${today.minute}`,
    `⏭️ أقرب موعد ظاهر في الشيت اليوم: ${next || "غير محدد"}`,
    "",
    "🟢 Telegram Webhook: متصل",
    "🟢 Google Sheets: متصل",
  ].join("\n");
}

async function handleCommand(env, text) {
  const command = text.split(/\s+/)[0].toLowerCase();
  if (command === "/start" || command === "/help") {
    return send(env, [
      "🤖 Khyrat Legal Content Engine",
      "",
      "/status — حالة النظام والشيت",
      "/today — ملخص منشورات اليوم",
      "/review — عدد المنشورات التي تحتاج مراجعة",
      "/failed — عدد المنشورات الفاشلة",
      "/tokens — حالة الاتصال الأساسية",
      "/help — هذه القائمة",
    ].join("\n"));
  }
  if (command === "/status" || command === "/today") return send(env, await statusText(env));
  if (command === "/review" || command === "/failed") {
    const values = await sheetValues(env);
    const rows = values.slice(1).map(rowToDict);
    const wanted = command === "/review"
      ? new Set(["NEEDS_REVIEW", "PENDING_REVIEW", "REVIEW"])
      : null;
    const matches = rows.filter((r) => {
      const s = String(r["الحالة"] || "").trim().toUpperCase();
      return wanted ? wanted.has(s) : s.includes("FAIL") || s === "ERROR";
    });
    if (!matches.length) return send(env, command === "/review" ? "🟢 لا توجد مراجعات معلقة حاليًا." : "🟢 لا توجد منشورات فاشلة حاليًا.");
    const lines = matches.slice(0, 10).map((r, i) => `${i + 1}) ${r["الموضوع"] || "بدون موضوع"} — ${r["الحالة"] || ""}`);
    return send(env, `${command === "/review" ? "🟡 المراجعات:" : "🔴 المنشورات الفاشلة:"}\n\n${lines.join("\n")}`);
  }
  if (command === "/tokens") {
    return send(env, "🔐 Token Manager\n\n🟡 Facebook: حالة التوكن تُدار من GitHub Secrets حاليًا.\n🟡 LinkedIn: حالة التوكن تُدار من GitHub Secrets حاليًا.\n\nسيتم ربط التجديد التلقائي والتنبيهات الفورية في طبقة Token Manager.");
  }
  return send(env, "❓ أمر غير معروف. اكتب /help لرؤية الأوامر المتاحة.");
}

async function handleCallback(env, callback) {
  const userId = String(callback.from?.id || "");
  if (userId !== String(env.TELEGRAM_ADMIN_USER_ID)) {
    return telegram(env, "answerCallbackQuery", { callback_query_id: callback.id, text: "⛔ غير مصرح لك.", show_alert: false });
  }
  const [action, rawRow] = String(callback.data || "").split(":");
  const rowNumber = Number(rawRow);
  if (!Number.isInteger(rowNumber) || rowNumber < 2) {
    return telegram(env, "answerCallbackQuery", { callback_query_id: callback.id, text: "بيانات الصف غير صالحة.", show_alert: false });
  }
  const values = await sheetValues(env);
  const row = values[rowNumber - 1] ? rowToDict(values[rowNumber - 1]) : null;
  if (!row) return telegram(env, "answerCallbackQuery", { callback_query_id: callback.id, text: "الصف غير موجود.", show_alert: false });
  const current = String(row["الحالة"] || "").trim().toUpperCase();
  if (!["NEEDS_REVIEW", "PENDING_REVIEW", "REVIEW"].includes(current)) {
    return telegram(env, "answerCallbackQuery", { callback_query_id: callback.id, text: `الحالة الحالية: ${current || "غير محددة"}`, show_alert: false });
  }
  if (action === "approve") {
    await updateSheetRow(env, rowNumber, { "الحالة": "APPROVED", "آخر خطأ": "" });
    await telegram(env, "answerCallbackQuery", { callback_query_id: callback.id, text: "تمت الموافقة.", show_alert: false });
    return telegram(env, "editMessageText", {
      chat_id: callback.message.chat.id,
      message_id: callback.message.message_id,
      text: `✅ تمت الموافقة على الصف ${rowNumber}.\n\nالموضوع: ${row["الموضوع"] || ""}\n\nسيُنشر في أقرب تشغيل للنشر.`,
    });
  }
  if (action === "reject") {
    await updateSheetRow(env, rowNumber, { "الحالة": "REJECTED", "آخر خطأ": "Rejected from Telegram review." });
    await telegram(env, "answerCallbackQuery", { callback_query_id: callback.id, text: "تم الرفض.", show_alert: false });
    return telegram(env, "editMessageText", {
      chat_id: callback.message.chat.id,
      message_id: callback.message.message_id,
      text: `❌ تم رفض الصف ${rowNumber}.\n\nالموضوع: ${row["الموضوع"] || ""}`,
    });
  }
  return telegram(env, "answerCallbackQuery", { callback_query_id: callback.id, text: "إجراء غير معروف.", show_alert: false });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === "GET" && url.pathname === "/health") {
      return Response.json({ ok: true, service: "khyrat-telegram-control", mode: "webhook" });
    }
    if (url.pathname !== "/telegram/webhook" || request.method !== "POST") {
      return new Response("Not found", { status: 404 });
    }
    if (env.TELEGRAM_WEBHOOK_SECRET && request.headers.get("X-Telegram-Bot-Api-Secret-Token") !== env.TELEGRAM_WEBHOOK_SECRET) {
      return new Response("Forbidden", { status: 403 });
    }
    try {
      const update = await request.json();
      if (update.callback_query) await handleCallback(env, update.callback_query);
      else if (update.message?.chat?.id && String(update.message.chat.id) === String(env.TELEGRAM_CHAT_ID)) {
        if (String(update.message.from?.id || "") === String(env.TELEGRAM_ADMIN_USER_ID)) await handleCommand(env, String(update.message.text || ""));
      }
      return new Response("OK");
    } catch (error) {
      console.error(error);
      try { await send(env, `🚨 Telegram Control Error\n\n${String(error?.message || error).slice(0, 1500)}`); } catch (_) {}
      return new Response("OK");
    }
  },
};

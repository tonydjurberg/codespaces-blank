const express = require("express");
const crypto = require("crypto");
const app = express();
app.use(express.json());

const PORT = process.env.PORT || 3000;
const VERIFY_TOKEN = process.env.WHATSAPP_VERIFY_TOKEN || "";
const ACCESS_TOKEN = process.env.WHATSAPP_ACCESS_TOKEN || "";
const PHONE_NUMBER_ID = process.env.WHATSAPP_PHONE_NUMBER_ID || "";
const APP_SECRET = process.env.META_APP_SECRET || "";

function verifySignature(req) {
  if (!APP_SECRET) return true;
  const signature = req.headers["x-hub-signature-256"] || "";
  const expected = "sha256=" + crypto.createHmac("sha256", APP_SECRET)
    .update(JSON.stringify(req.body)).digest("hex");
  return crypto.timingSafeEqual(Buffer.from(signature), Buffer.from(expected));
}

app.get("/webhook", (req, res) => {
  if (req.query["hub.mode"] === "subscribe" &&
      req.query["hub.verify_token"] === VERIFY_TOKEN) {
    return res.status(200).send(req.query["hub.challenge"]);
  }
  res.sendStatus(403);
});

app.post("/webhook", (req, res) => {
  if (!verifySignature(req)) return res.sendStatus(403);
  console.log("WhatsApp webhook:", JSON.stringify(req.body));
  res.sendStatus(200);
});

app.post("/api/send-message", async (req, res) => {
  const { to, text } = req.body || {};
  if (!to || !text) return res.status(400).json({ error: "to and text are required" });
  if (!ACCESS_TOKEN || !PHONE_NUMBER_ID) {
    return res.status(503).json({ error: "WhatsApp Cloud API is not configured" });
  }

  const response = await fetch(
    `https://graph.facebook.com/v23.0/${PHONE_NUMBER_ID}/messages`,
    {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${ACCESS_TOKEN}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        messaging_product: "whatsapp",
        to,
        type: "text",
        text: { body: text }
      })
    }
  );

  const data = await response.json();
  res.status(response.ok ? 200 : response.status).json(data);
});

app.get("/health", (req, res) => res.json({
  ok: true,
  whatsappConfigured: Boolean(ACCESS_TOKEN && PHONE_NUMBER_ID)
}));

app.listen(PORT, () => console.log(`WhatsApp CRM API listening on port ${PORT}`));

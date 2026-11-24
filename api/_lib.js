// Shared helpers for the rank-alert endpoints.
// No npm packages: Node 18+ on Vercel has fetch and crypto built in.

const crypto = require('crypto');

const DATA_URL = process.env.DATA_URL
  || 'https://raw.githubusercontent.com/Vidanth-Tennis/Project-Vctra/main/data.json';
const SITE = (process.env.SITE_URL || 'https://vctra.vercel.app').replace(/\/+$/, '');

/* ---------- Upstash Redis over its REST API ---------- */
async function redis(...command) {
  const url = process.env.UPSTASH_REDIS_REST_URL;
  const token = process.env.UPSTASH_REDIS_REST_TOKEN;
  if (!url || !token) throw new Error('Redis is not configured');
  const r = await fetch(url, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(command),
  });
  if (!r.ok) throw new Error(`Redis ${r.status}: ${(await r.text()).slice(0, 200)}`);
  const out = await r.json();
  if (out.error) throw new Error(`Redis: ${out.error}`);
  return out.result;
}

const getJSON = async (key) => {
  const v = await redis('GET', key);
  try { return v ? JSON.parse(v) : null; } catch { return null; }
};

/* ---------- email via Brevo ---------- */
async function sendMail(to, subject, html, text) {
  const key = process.env.BREVO_API_KEY;
  if (!key) throw new Error('Email sending is not configured');
  const r = await fetch('https://api.brevo.com/v3/smtp/email', {
    method: 'POST',
    headers: { 'api-key': key, 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({
      sender: {
        name: process.env.SENDER_NAME || 'Vctra Rank Alerts',
        email: process.env.SENDER_EMAIL,
      },
      to: [{ email: to }],
      subject,
      htmlContent: html,
      textContent: text,
    }),
  });
  if (!r.ok) throw new Error(`Brevo ${r.status}: ${(await r.text()).slice(0, 300)}`);
  return true;
}

/* ---------- small utilities ---------- */
const token = () => crypto.randomBytes(24).toString('hex');

// Deliberately simple: catches typos without rejecting unusual but valid addresses.
const validEmail = (e) =>
  typeof e === 'string' && e.length <= 254 && /^[^\s@]+@[^\s@]+\.[a-z]{2,}$/i.test(e.trim());

const cleanEmail = (e) => String(e).trim().toLowerCase();

const esc = (s) => String(s).replace(/[&<>"']/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

let dataCache = null;
let dataCacheAt = 0;
async function rankings() {
  if (dataCache && Date.now() - dataCacheAt < 60_000) return dataCache;
  const r = await fetch(DATA_URL, { headers: { 'User-Agent': 'vctra-alerts' } });
  if (!r.ok) throw new Error(`Could not read rankings (${r.status})`);
  dataCache = await r.json();
  dataCacheAt = Date.now();
  return dataCache;
}

/** Find a player's row in a category. Returns {rank, name, pts} or null. */
function findPlayer(data, aita, cat) {
  const rows = (data.categories || {})[cat];
  if (!rows) return null;
  const row = rows.find((p) => String(p[2]) === String(aita));
  return row ? { rank: row[0], name: row[1], pts: row[4] } : null;
}

/** A plain page, so a click on a confirm or unsubscribe link lands somewhere human. */
function page(res, title, body, code = 200) {
  res.status(code).setHeader('Content-Type', 'text/html; charset=utf-8');
  res.send(`<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(title)}</title>
<style>
  :root{color-scheme:dark}
  body{margin:0;min-height:100vh;display:grid;place-items:center;padding:24px;
    background:#0a2f1c;color:#f5f1e6;
    font-family:'Barlow',system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif}
  .card{max-width:30rem;width:100%;background:#0d1b3a;border:2px solid #1457c8;
    border-radius:14px;padding:1.6rem 1.4rem;text-align:center;
    box-shadow:0 14px 40px rgba(0,0,0,.45)}
  h1{font-family:'Barlow Semi Condensed',Arial Narrow,sans-serif;text-transform:uppercase;
    letter-spacing:.03em;font-size:1.7rem;margin:0 0 .6rem}
  p{line-height:1.6;margin:.5rem 0;font-weight:500}
  a.btn{display:inline-block;margin-top:1.1rem;background:#1f6feb;color:#fff;
    text-decoration:none;padding:.65rem 1.3rem;border-radius:9px;font-weight:700;
    text-transform:uppercase;letter-spacing:.06em}
</style></head><body><div class="card">${body}
<a class="btn" href="${SITE}">Back to Vctra</a></div></body></html>`);
}

module.exports = {
  redis, getJSON, sendMail, token, validEmail, cleanEmail, esc,
  rankings, findPlayer, page, SITE,
};

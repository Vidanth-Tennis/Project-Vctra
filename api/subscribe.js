// POST { email, aita, cat } -> stores a PENDING signup and emails a confirm link.
// Nothing is stored as a real subscription until that link is clicked, so nobody
// can sign up somebody else's address.

const {
  redis, sendMail, token, validEmail, cleanEmail, esc,
  rankings, findPlayer, SITE,
} = require('./_lib');

const PENDING_TTL = 60 * 60 * 48;   // confirm links last 48 hours
const MAX_PER_IP_PER_DAY = 10;

module.exports = async (req, res) => {
  res.setHeader('Content-Type', 'application/json');
  if (req.method !== 'POST') {
    return res.status(405).json({ ok: false, error: 'Use POST.' });
  }

  try {
    const body = typeof req.body === 'string' ? JSON.parse(req.body || '{}') : (req.body || {});
    const email = cleanEmail(body.email || '');
    const aita = String(body.aita || '').trim();
    const cat = String(body.cat || '').trim();

    if (!validEmail(email)) {
      return res.status(400).json({ ok: false, error: "That email address doesn't look right." });
    }
    if (!/^\d{4,8}$/.test(aita)) {
      return res.status(400).json({ ok: false, error: 'That AITA number doesn\'t look right.' });
    }

    // Soft rate limit per IP, so the form can't be used to spam people.
    const ip = (req.headers['x-forwarded-for'] || '').split(',')[0].trim() || 'unknown';
    const day = new Date().toISOString().slice(0, 10);
    const rlKey = `rl:${ip}:${day}`;
    const hits = await redis('INCR', rlKey);
    if (hits === 1) await redis('EXPIRE', rlKey, 86400);
    if (hits > MAX_PER_IP_PER_DAY) {
      return res.status(429).json({ ok: false, error: 'Too many signups from here today. Try again tomorrow.' });
    }

    // The player must actually exist in that category.
    const data = await rankings();
    const player = findPlayer(data, aita, cat);
    if (!player) {
      return res.status(404).json({ ok: false, error: `No player with AITA ${esc(aita)} in ${esc(cat)}.` });
    }

    // Already subscribed? Say the same thing either way, so the form can't be
    // used to find out whether an address is on the list.
    const idx = `idx:${aita}:${cat}:${email}`;
    if (await redis('GET', idx)) {
      return res.status(200).json({ ok: true, message: 'Check your email to finish signing up.' });
    }

    const t = token();
    await redis('SET', `pend:${t}`,
      JSON.stringify({ email, aita, cat, name: player.name, rank: player.rank, at: Date.now() }),
      'EX', String(PENDING_TTL));

    const link = `${SITE}/api/confirm?t=${t}`;
    const who = `${esc(player.name)} (AITA ${esc(aita)})`;
    await sendMail(
      email,
      'Confirm your Vctra rank alerts',
      `<div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.6;color:#222">
        <p>Someone asked for rank alerts for <strong>${who}</strong> in <strong>${esc(cat)}</strong>, currently ranked <strong>#${player.rank}</strong>.</p>
        <p>If that was you, confirm it here:</p>
        <p><a href="${link}" style="background:#1f6feb;color:#fff;text-decoration:none;padding:11px 20px;border-radius:8px;display:inline-block;font-weight:bold">Yes, send me rank alerts</a></p>
        <p style="color:#666;font-size:13px">If it wasn't you, ignore this email and nothing happens. The link stops working in 48 hours.</p>
        <p style="color:#666;font-size:13px">If you are under 18, please check with a parent before confirming.</p>
      </div>`,
      `Confirm rank alerts for ${player.name} (AITA ${aita}) in ${cat}, currently #${player.rank}.\n\n${link}\n\nIf this wasn't you, ignore this email. The link expires in 48 hours.`
    );

    return res.status(200).json({ ok: true, message: 'Check your email to finish signing up.' });
  } catch (err) {
    console.error('subscribe failed:', err);
    return res.status(500).json({ ok: false, error: 'Something went wrong. Please try again later.' });
  }
};

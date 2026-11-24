// GET /api/confirm?t=<token> -> turns a pending signup into a real one.

const { redis, getJSON, esc, page } = require('./_lib');

module.exports = async (req, res) => {
  const t = String((req.query && req.query.t) || '').trim();
  if (!/^[a-f0-9]{48}$/.test(t)) {
    return page(res, 'Link not valid',
      '<h1>Link not valid</h1><p>That confirmation link is incomplete. Try signing up again.</p>', 400);
  }

  try {
    const pend = await getJSON(`pend:${t}`);
    if (!pend) {
      return page(res, 'Link expired',
        '<h1>Link expired</h1><p>Confirmation links last 48 hours. Sign up again and we will send a fresh one.</p>', 410);
    }

    const idx = `idx:${pend.aita}:${pend.cat}:${pend.email}`;
    const existing = await redis('GET', idx);
    if (existing) {
      await redis('DEL', `pend:${t}`);
      return page(res, 'Already set up',
        `<h1>Already set up</h1><p>You were already getting alerts for <strong>${esc(pend.name)}</strong> in ${esc(pend.cat)}.</p>`);
    }

    await redis('SET', `sub:${t}`, JSON.stringify({
      email: pend.email, aita: pend.aita, cat: pend.cat,
      name: pend.name, lastRank: pend.rank, since: Date.now(),
    }));
    await redis('SET', idx, t);
    await redis('SADD', 'subs', t);
    await redis('DEL', `pend:${t}`);

    return page(res, 'You are on the list',
      `<h1>You're on the list</h1>
       <p>We'll email you when <strong>${esc(pend.name)}</strong> moves in <strong>${esc(pend.cat)}</strong>.</p>
       <p>Current rank: <strong>#${esc(pend.rank)}</strong></p>
       <p style="color:#9fb4da;font-size:14px">Rankings update about once a week, so don't expect mail every day. Every alert has an unsubscribe link.</p>`);
  } catch (err) {
    console.error('confirm failed:', err);
    return page(res, 'Something went wrong',
      '<h1>Something went wrong</h1><p>Please try again in a few minutes.</p>', 500);
  }
};

// GET /api/unsubscribe?t=<token> -> removes a subscription, no questions asked.

const { redis, getJSON, esc, page } = require('./_lib');

module.exports = async (req, res) => {
  const t = String((req.query && req.query.t) || '').trim();
  if (!/^[a-f0-9]{48}$/.test(t)) {
    return page(res, 'Link not valid',
      '<h1>Link not valid</h1><p>That unsubscribe link is incomplete.</p>', 400);
  }

  try {
    const sub = await getJSON(`sub:${t}`);
    // Always report success: an unsubscribe link should never fail on someone.
    if (sub) {
      await redis('DEL', `sub:${t}`);
      await redis('DEL', `idx:${sub.aita}:${sub.cat}:${sub.email}`);
      await redis('SREM', 'subs', t);
    }
    return page(res, 'Unsubscribed',
      `<h1>Unsubscribed</h1><p>${sub
        ? `No more alerts for <strong>${esc(sub.name)}</strong> in ${esc(sub.cat)}.`
        : 'That subscription is already gone.'}</p>
       <p style="color:#9fb4da;font-size:14px">Your address has been deleted. You can sign up again any time.</p>`);
  } catch (err) {
    console.error('unsubscribe failed:', err);
    return page(res, 'Something went wrong',
      '<h1>Something went wrong</h1><p>Please try again in a few minutes.</p>', 500);
  }
};

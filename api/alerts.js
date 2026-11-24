// Daily job: compare each subscriber's stored rank with the live list and email
// anyone whose rank moved. Vercel calls this on the schedule in vercel.json.

const {
  redis, getJSON, sendMail, esc, rankings, findPlayer, SITE,
} = require('./_lib');

// Brevo's free plan allows 300 emails a day. Stay under it; anyone not emailed
// today still has an out-of-date stored rank, so they are picked up tomorrow.
const DAILY_SEND_CAP = Number(process.env.DAILY_SEND_CAP || 280);

function emailBody(sub, oldRank, newRank, unsubLink) {
  const moved = oldRank - newRank;            // positive = improved
  const up = moved > 0;
  const word = up ? 'up' : 'down';
  const colour = up ? '#1a7f37' : '#b3261e';
  const places = Math.abs(moved);
  const headline = `${esc(sub.name)} moved ${word} ${places} place${places === 1 ? '' : 's'}`;

  return {
    subject: `#${newRank} in ${sub.cat} — ${up ? 'up' : 'down'} ${places}`,
    html: `<div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.6;color:#222">
      <p style="font-size:19px;margin:0 0 6px"><strong>${headline}</strong></p>
      <p style="margin:0 0 14px;color:#555">${esc(sub.cat)}</p>
      <p style="font-size:30px;margin:0;color:${colour}"><strong>#${oldRank} &rarr; #${newRank}</strong></p>
      <p style="margin:18px 0"><a href="${SITE}" style="background:#1f6feb;color:#fff;text-decoration:none;padding:11px 20px;border-radius:8px;display:inline-block;font-weight:bold">See the full ranking</a></p>
      <p style="color:#888;font-size:12px;margin-top:26px">
        You asked for alerts for AITA ${esc(sub.aita)}.
        <a href="${unsubLink}" style="color:#888">Unsubscribe</a>.
      </p>
    </div>`,
    text: `${sub.name} moved ${word} ${places} place${places === 1 ? '' : 's'} in ${sub.cat}.\n`
        + `#${oldRank} -> #${newRank}\n\n${SITE}\n\nUnsubscribe: ${unsubLink}`,
  };
}

module.exports = async (req, res) => {
  // Vercel sends this header on scheduled runs when CRON_SECRET is set.
  const secret = process.env.CRON_SECRET;
  if (secret && req.headers.authorization !== `Bearer ${secret}`) {
    return res.status(401).json({ ok: false, error: 'Not authorised' });
  }

  const started = Date.now();
  const report = { checked: 0, moved: 0, sent: 0, failed: 0, gone: 0, capped: false };

  try {
    const data = await rankings();
    const tokens = (await redis('SMEMBERS', 'subs')) || [];

    for (const t of tokens) {
      if (report.sent >= DAILY_SEND_CAP) { report.capped = true; break; }

      const sub = await getJSON(`sub:${t}`);
      if (!sub) { await redis('SREM', 'subs', t); report.gone++; continue; }
      report.checked++;

      const player = findPlayer(data, sub.aita, sub.cat);
      // Dropping off a list entirely is normal (age group changes); leave the
      // stored rank alone rather than inventing a movement.
      if (!player) continue;

      const oldRank = Number(sub.lastRank);
      const newRank = Number(player.rank);
      if (!Number.isFinite(oldRank) || !Number.isFinite(newRank) || oldRank === newRank) continue;

      report.moved++;
      const mail = emailBody(sub, oldRank, newRank, `${SITE}/api/unsubscribe?t=${t}`);
      try {
        await sendMail(sub.email, mail.subject, mail.html, mail.text);
        report.sent++;
        // Only record the new rank once the email actually went out, so a
        // failed send is retried tomorrow instead of being lost.
        sub.lastRank = newRank;
        sub.name = player.name;
        await redis('SET', `sub:${t}`, JSON.stringify(sub));
      } catch (e) {
        report.failed++;
        console.error(`send failed for ${t}:`, e.message);
      }
    }

    report.ms = Date.now() - started;
    console.log('alert run:', JSON.stringify(report));
    return res.status(200).json({ ok: true, ...report });
  } catch (err) {
    console.error('alert run failed:', err);
    return res.status(500).json({ ok: false, error: String(err.message || err), ...report });
  }
};

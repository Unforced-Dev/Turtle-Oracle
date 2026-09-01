/* Port of app/oracle/lore.py — the Tale-Book, the shell's memory of returning seekers.
 *
 * The playa version is an append-only JSONL file that lives and dies with one week in a
 * tent. A Worker has no filesystem, so the book lives in the same KV namespace as the
 * séances under a `lore:` prefix — but on a public deployment "the shell remembers you"
 * is also "anyone who guesses your name reads your record". The per-name records
 * therefore expire after thirty days, which is longer than a burn and shorter than
 * forever; only the anonymous tallies behind the attract screen are kept.
 *
 * Deliberate shape change: the Python re-reads and re-scans the whole log on every
 * lookup. KV has no scan, so the book is kept two ways —
 *   lore:name:<normalised>  the last few records for one seeker (that is all
 *                           last_quest / last_tale ever need)
 *   lore:counts             {sealed, tales, recent_titles} for the attract screen
 * Both are read-modify-write, so two seekers sealing in the same second could lose one
 * tick off a counter. That is a display number on the attract loop, not the ledger.
 */

const PER_NAME_KEEP = 8;
const RECENT_TITLES = 5;
const NAME_TTL = 30 * 24 * 60 * 60;

function norm(name) {
  return (name || "").toLowerCase().replace(/[^a-z0-9]+/g, "");
}

function stamp() {
  return {
    ts: Date.now() / 1000,
    when: new Intl.DateTimeFormat("en-US", {
      timeZone: "America/Los_Angeles",
      weekday: "short",
      month: "short",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    })
      .formatToParts(new Date())
      .reduce((acc, p) => {
        acc[p.type] = p.value;
        return acc;
      }, {}),
  };
}

function whenString() {
  const p = stamp().when;
  return `${p.weekday} ${p.month} ${p.day} ${p.hour}:${p.minute}`;
}

async function readJson(kv, key, fallback) {
  try {
    const v = await kv.get(key, "json");
    return v == null ? fallback : v;
  } catch (e) {
    return fallback;
  }
}

export async function append(kv, rec) {
  if (!kv) return;
  const full = { ...rec, ts: Date.now() / 1000, when: whenString() };
  const n = norm(rec.name);
  try {
    if (n) {
      const key = `lore:name:${n}`;
      const list = await readJson(kv, key, []);
      list.push(full);
      // the TTL rides on every write, so an active seeker's record keeps sliding
      // forward and a one-night seeker's record falls off the shelf
      await kv.put(key, JSON.stringify(list.slice(-PER_NAME_KEEP)), { expirationTtl: NAME_TTL });
    }
    const counts = await readJson(kv, "lore:counts", {
      sealed: 0,
      tales: 0,
      recent_titles: [],
    });
    if (rec.type === "quest") {
      counts.sealed = (counts.sealed || 0) + 1;
      counts.recent_titles = [rec.title || "", ...(counts.recent_titles || [])].slice(
        0,
        RECENT_TITLES,
      );
    } else if (rec.type === "tale") {
      counts.tales = (counts.tales || 0) + 1;
    }
    await kv.put("lore:counts", JSON.stringify(counts));
  } catch (e) {
    /* The Tale-Book failing must never cost a seeker their quest. */
  }
}

async function find(kv, name) {
  const n = norm(name);
  if (!kv || !n) return [];
  return await readJson(kv, `lore:name:${n}`, []);
}

export async function lastQuest(kv, name) {
  const rs = (await find(kv, name)).filter((r) => r.type === "quest");
  return rs.length ? rs[rs.length - 1] : null;
}

export async function lastTale(kv, name) {
  const rs = (await find(kv, name)).filter((r) => r.type === "tale");
  return rs.length ? rs[rs.length - 1] : null;
}

export async function counts(kv) {
  const c = await readJson(kv, "lore:counts", { sealed: 0, tales: 0, recent_titles: [] });
  return {
    sealed: c.sealed || 0,
    tales: c.tales || 0,
    /* lore.py stores oldest-first and reverses on read; here the list is already
     * newest-first, so it is served as-is. */
    recent_titles: (c.recent_titles || []).slice(0, RECENT_TITLES),
  };
}

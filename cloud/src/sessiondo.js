/* One Durable Object per séance — the thing KV could not be.
 *
 * The session used to live in KV under sess:<id>. KV is eventually consistent by
 * design: a read is cached at the location that served it for up to 60s and a write
 * does NOT invalidate that cache. Cloudflare's own words — "Visibility of changes takes
 * longer in locations which have recently read a previous version of a given key... If
 * you need stronger consistency guarantees, consider using Durable Objects."
 *
 * A séance is a state machine driven by consecutive POSTs seconds apart, so that is
 * exactly the wrong storage. Observed in production: a seeker answered the stem, the
 * next request read the pre-stem session back out of the edge cache, and their answer
 * was consumed as their NAME — bouncing them to the weather picker with the stage
 * rolled back underneath them.
 *
 * A Durable Object is one object, in one place, single-threaded: two requests for the
 * same session id queue behind each other and the second always sees the first's write.
 * `idFromName(sid)` makes the séance id the address, so there is no directory to keep.
 *
 * Storage is SQLite-backed (`new_sqlite_classes` in wrangler.toml) because that is the
 * only Durable Object storage on the Workers free plan. The key-value methods below run
 * on top of it; nothing here needs SQL.
 *
 * The 2h TTL KV gave for free is done by hand two ways, because either alone has a
 * hole: an `expires` stamp checked on read (so a stale session is never served even if
 * the alarm has not fired) and a storage alarm (so an abandoned session deletes itself
 * rather than sitting on the shelf forever).
 *
 * The Tale-Book (lore:*) and the tiers counter stay in KV on purpose. They are
 * best-effort counters and a name index, they are read minutes or days after they are
 * written, and eventual consistency is the right trade for them.
 */
import { DurableObject } from "cloudflare:workers";

const DEFAULT_TTL = 7200;
const KEY = "sess";

export class SessionDO extends DurableObject {
  /** The séance, or null if there never was one or it has aged out. */
  async load() {
    const rec = await this.ctx.storage.get(KEY);
    if (!rec || !rec.sess) return null;
    if (!rec.expires || rec.expires <= Date.now()) {
      await this.drop();
      return null;
    }
    return rec.sess;
  }

  /** Write the séance back and slide its expiry forward, as KV's TTL-per-put did. */
  async save(sess, ttl) {
    if (!sess) return;
    const secs = Number(ttl) > 0 ? Number(ttl) : DEFAULT_TTL;
    const expires = Date.now() + secs * 1000;
    await this.ctx.storage.put(KEY, { sess, expires });
    await this.ctx.storage.setAlarm(expires);
  }

  async drop() {
    await this.ctx.storage.deleteAlarm();
    await this.ctx.storage.deleteAll();
  }

  /** The 2h roof, arriving on its own. An abandoned séance costs nothing after this. */
  async alarm() {
    await this.ctx.storage.deleteAll();
  }
}

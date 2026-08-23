/* Small shared helpers: randomness, word math, and Black Rock City wall-clock.
 *
 * The Python app leans on `random` and `datetime.now()`. A Worker has neither a
 * seeded RNG worth trusting nor a local timezone — it runs in UTC in whatever
 * datacentre took the request — so both are rebuilt here explicitly.
 */

/* Burning Man is on Pacific time. A cloud turtle answering from Frankfurt must
 * still say "it is deep night" when it is deep night on the playa. */
export const TZ = "America/Los_Angeles";

const _buf = new Uint32Array(1);

/** Uniform float in [0, 1) — crypto-backed, unlike Math.random in a cold isolate. */
export function rand() {
  crypto.getRandomValues(_buf);
  return _buf[0] / 4294967296;
}

export function randRange(n) {
  return Math.floor(rand() * n) % n;
}

export function choice(arr) {
  return arr[randRange(arr.length)];
}

/** len(s.split()) */
export function words(s) {
  return ((s || "").trim().match(/\S+/g) || []).length;
}

/** Python str.rstrip(chars) */
export function rstrip(s, chars) {
  let end = s.length;
  while (end > 0 && chars.includes(s[end - 1])) end--;
  return s.slice(0, end);
}

/** Python str.center(width) — extra pad lands on the right, per CPython's formula. */
export function center(s, width) {
  s = s.slice(0, width);
  const marg = width - s.length;
  if (marg <= 0) return s;
  const left = (marg >> 1) + (marg & width & 1);
  return " ".repeat(left) + s + " ".repeat(marg - left);
}

/** textwrap.wrap(s, width) or [""] */
export function wrap(s, width) {
  const out = [];
  let line = "";
  for (let w of (s || "").split(/\s+/).filter(Boolean)) {
    while (w.length > width) {
      // break_long_words=True: a URL or a very long token gets chopped, not overflowed
      if (line) {
        out.push(line);
        line = "";
      }
      out.push(w.slice(0, width));
      w = w.slice(width);
    }
    if (!line) line = w;
    else if (line.length + 1 + w.length <= width) line += " " + w;
    else {
      out.push(line);
      line = w;
    }
  }
  if (line) out.push(line);
  return out.length ? out : [""];
}

/** re.split(r"(?<=[.!?])\s+", text)[0] */
export function firstSentence(text) {
  text = (text || "").trim();
  const parts = text
    .split(/(?<=[.!?])\s+/)
    .map((p) => p.trim())
    .filter(Boolean);
  return parts.length ? parts[0] : text;
}

export function shortWords(text, limit) {
  const w = (text || "").split(/\s+/).filter(Boolean);
  if (w.length <= limit) return w.join(" ");
  return rstrip(w.slice(0, limit).join(" "), " ,;:—-") + "…";
}

/* ---- Black Rock City wall clock -------------------------------------------------- */

const _weekdayFmt = new Intl.DateTimeFormat("en-US", { timeZone: TZ, weekday: "long" });
const _clockFmt = new Intl.DateTimeFormat("en-US", {
  timeZone: TZ,
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

/** {weekday, hour (0-23), minute} on the playa, right now. */
export function brcNow() {
  const now = new Date();
  const parts = Object.fromEntries(
    _clockFmt.formatToParts(now).map((p) => [p.type, p.value]),
  );
  let hour = parseInt(parts.hour, 10);
  if (hour === 24) hour = 0; // some ICU builds render midnight as 24 in h23/h24 modes
  return {
    weekday: _weekdayFmt.format(now),
    hour,
    minute: parseInt(parts.minute, 10),
  };
}

/** strftime('%A, %I:%M %p').replace(' 0', ' ') — built by hand so ICU can't drift it. */
export function brcClockString() {
  const { weekday, hour, minute } = brcNow();
  const h12 = hour % 12 || 12;
  const mm = String(minute).padStart(2, "0");
  return `${weekday}, ${h12}:${mm} ${hour < 12 ? "AM" : "PM"}`;
}

/** time.strftime("%a %b %d  %H:%M") on the playa — for the receipt header. */
export function brcStamp() {
  const now = new Date();
  const p = Object.fromEntries(
    new Intl.DateTimeFormat("en-US", {
      timeZone: TZ,
      weekday: "short",
      month: "short",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    })
      .formatToParts(now)
      .map((x) => [x.type, x.value]),
  );
  return `${p.weekday} ${p.month} ${p.day}  ${p.hour}:${p.minute}`;
}

export function json(body, status = 200, extra = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
      ...extra,
    },
  });
}

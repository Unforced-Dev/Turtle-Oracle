/* Every test the cloud turtle has, in one run.
 *
 *   TZ=America/Los_Angeles npm test
 *
 * Every file is run even when an earlier one fails, because "the prompts drifted", "the
 * state machine broke" and "the city went dark" are different problems and you want to
 * see all of them at once. parity.mjs needs python3 on PATH; seance.mjs and city.mjs
 * need nothing at all — city.mjs runs against assets/city.json when tools/build_city.py
 * has made one and against its own fixture when it has not.
 */
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SUITES = [
  ["the séance state machine", "seance.mjs"],
  ["the city, the chat, and the routes", "city.mjs"],
  ["prompt parity with app/oracle", "parity.mjs"],
];

const failed = [];
for (const [label, file] of SUITES) {
  console.log(`\n══ ${label} — test/${file}`);
  const r = spawnSync(process.execPath, [path.join(HERE, file)], { stdio: "inherit" });
  if (r.status !== 0) failed.push(file);
}

console.log(failed.length ? `\n${failed.join(" and ")} FAILED` : "\nALL PASS");
process.exit(failed.length ? 1 : 0);

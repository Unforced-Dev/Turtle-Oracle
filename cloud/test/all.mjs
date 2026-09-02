/* Every test the cloud turtle has, in one run.
 *
 *   TZ=America/Los_Angeles npm test
 *
 * Both files are run even when the first one fails, because "the prompts drifted" and
 * "the state machine broke" are different problems and you want to see both at once.
 * parity.mjs needs python3 on PATH; seance.mjs needs nothing at all.
 */
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SUITES = [
  ["the séance state machine", "seance.mjs"],
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

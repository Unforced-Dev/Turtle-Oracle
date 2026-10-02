/* Port of app/oracle/printer.py — format only.
 *
 * The cloud turtle has no thermal printer and never will: it is the backup that runs
 * when the Spark is off, and it answers phones on the open internet. print_or_preview()
 * therefore has no counterpart here — /api/print formats the receipt and returns
 * {"status": "preview"}, which is exactly what the kiosk already handles (it toasts
 * "No printer attached"). The formatter itself is kept whole so the text a seeker could
 * screenshot is byte-for-byte the paper they would have got at camp.
 */
import { COMPASS_ROSE, directionsLines } from "./geo.js";
import { center, wrap, brcStamp } from "./util.js";

// 80mm / font A = 48 cols on the TM-m30III; 58mm printers are 32.
const WIDTH = 48;

const rule = (ch = "-") => ch.repeat(WIDTH);

function centerBlock(block) {
  const lines = block.split("\n");
  const pad = Math.max(0, Math.floor((WIDTH - Math.max(...lines.map((l) => l.length))) / 2));
  return lines.map((l) => " ".repeat(pad) + l).join("\n");
}

export function formatReceipt(payload, picks, located, quest) {
  const L = [];
  const push = (arr) => arr.forEach((x) => L.push(x));
  L.push(center("* THE TERRIBLE TURTLE *", WIDTH));
  L.push(center("ORACLE", WIDTH));
  L.push(center("Move Slow & Bite Things", WIDTH));
  L.push(rule("="));
  L.push(brcStamp());
  L.push("");
  L.push("YOU TOLD THE TURTLE:");
  push(wrap(payload.question, WIDTH));
  L.push("");
  L.push(rule());
  L.push("THE TREE DREW:");
  const labels = { roots: "FACE", trunk: "STAND", branches: "REACH" };
  for (const realm of ["roots", "trunk", "branches"]) {
    const c = picks[realm];
    // a Shell card standing in a Tree slot is the axis; say so on the paper too, so
    // the seeker still has the evidence of it days later
    const label = c.realm === "shell" ? "* AXIS *" : labels[realm];
    push(wrap(`[${label}] ${c.name}`, WIDTH));
  }
  L.push(rule());
  L.push("");
  L.push("THE READING");
  push(wrap(payload.reading, WIDTH));
  L.push("");
  if (quest) {
    L.push(rule("="));
    push(wrap(quest.title.toUpperCase(), WIDTH));
    if (quest.for) L.push(center(`sealed for ${quest.for}`, WIDTH));
    L.push(rule("="));
    push(wrap(quest.charge, WIDTH));
    L.push("");
    quest.moves.forEach((m, i) => {
      // cloud: the quest is ONE bite here, so the paper says so rather than numbering a
      // list of one. A quest sealed by the Spark still comes through with three moves.
      const head = quest.moves.length > 1 ? `MOVE ${i + 1}` : "THE ONE BITE";
      push(wrap(`${head} [${m.slot}] ${m.card}`, WIDTH));
      push(wrap(m.task, WIDTH));
      push(wrap("@ " + m.where, WIDTH));
      push(wrap("PROOF: " + m.proof, WIDTH));
      if (m.leave) push(wrap("LEAVE: " + m.leave, WIDTH));
      L.push("");
    });
    L.push(rule());
    L.push("THE VOW");
    push(wrap(quest.vow, WIDTH));
    push(wrap("(" + quest.vow_where + ")", WIDTH));
    L.push("");
    push(wrap(quest.chosen || "", WIDTH));
    L.push("");
  } else {
    L.push("YOUR QUEST");
    push(wrap(payload.adventure, WIDTH));
    L.push("");
  }
  L.push(rule());
  L.push("WHERE TO GO");
  L.push(centerBlock(COMPASS_ROSE));
  L.push("");
  for (const line of directionsLines(picks, located)) {
    push(wrap("> " + line, WIDTH));
    L.push("");
  }
  L.push(rule("="));
  L.push(center("there's a spot", WIDTH));
  L.push(center("in the shell for you", WIDTH));
  L.push("");
  return L.join("\n");
}

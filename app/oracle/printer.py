"""Thermal receipt: format the reading + quest for an ESC/POS printer.

The camp runs Epson TM-m30III units: 80mm paper, 48 columns in font A. Set
ORACLE_PRINT_WIDTH to 32 for a 58mm printer.

Transport, in order of preference:
  ESCPOS_HOST            -> network printer on port 9100 (the TM-m30III's ethernet port;
                            one cable to the camp router, nothing to kick loose)
  ESCPOS_VENDOR_ID/_PRODUCT_ID -> USB
  neither                -> save a text preview to app/receipts/ so you can see exactly
                            what would have printed
"""
import os
import textwrap
import time

from .deck import REPO
from .geo import COMPASS_ROSE, directions_lines

# 80mm / font A = 48 cols on the TM-m30III; 58mm printers are 32.
WIDTH = int(os.environ.get("ORACLE_PRINT_WIDTH", "48"))
PROFILE = os.environ.get("ESCPOS_PROFILE", "TM-m30")
RECEIPTS = os.path.join(REPO, "app", "receipts")


def _rule(ch="-"):
    return ch * WIDTH


def _center(s):
    return s[:WIDTH].center(WIDTH)


def _wrap(s):
    return textwrap.wrap(s, WIDTH) or [""]


def _center_block(block):
    """Centre a fixed-width ASCII block (the compass rose) inside WIDTH.

    The rose is hand-drawn at <=32 cols; on 80mm paper it would otherwise hug the
    left edge while everything around it fills the width.
    """
    lines = block.split("\n")
    pad = max(0, (WIDTH - max(len(l) for l in lines)) // 2)
    return "\n".join(" " * pad + l for l in lines)


def format_receipt(payload, picks, located, quest=None):
    L = []
    L.append(_center("* THE TERRIBLE TURTLE *"))
    L.append(_center("ORACLE"))
    L.append(_center("Move Slow & Bite Things"))
    L.append(_rule("="))
    L.append(time.strftime("%a %b %d  %H:%M"))
    L.append("")
    L.append("YOU TOLD THE TURTLE:")
    L.extend(_wrap(payload["question"]))
    L.append("")
    L.append(_rule())
    L.append("THE TREE DREW:")
    labels = {"roots": "FACE", "trunk": "STAND", "branches": "REACH"}
    for realm in ("roots", "trunk", "branches"):
        c = picks[realm]
        # a Shell card standing in a Tree slot is the axis; say so on the paper too, so
        # the seeker still has the evidence of it days later
        label = "* AXIS *" if c.get("realm") == "shell" else labels[realm]
        L.extend(_wrap(f"[{label}] {c['name']}"))
    L.append(_rule())
    L.append("")
    L.append("THE READING")
    L.extend(_wrap(payload["reading"]))
    L.append("")
    if quest:
        L.append(_rule("="))
        L.extend(_wrap(quest["title"].upper()))
        if quest.get("for"):
            L.append(_center(f"sealed for {quest['for']}"))
        L.append(_rule("="))
        L.extend(_wrap(quest["charge"]))
        L.append("")
        for i, m in enumerate(quest["moves"], 1):
            L.extend(_wrap(f"MOVE {i} [{m['slot']}] {m['card']}"))
            L.extend(_wrap(m["task"]))
            L.extend(_wrap("@ " + m["where"]))
            L.extend(_wrap("PROOF: " + m["proof"]))
            if m.get("leave"):
                L.extend(_wrap("LEAVE: " + m["leave"]))
            L.append("")
        L.append(_rule())
        L.append("THE VOW")
        L.extend(_wrap(quest["vow"]))
        L.extend(_wrap("(" + quest["vow_where"] + ")"))
        L.append("")
        L.extend(_wrap(quest.get("chosen", "")))
        L.append("")
    else:
        L.append("YOUR QUEST")
        L.extend(_wrap(payload["adventure"]))
        L.append("")
    L.append(_rule())
    L.append("WHERE TO GO")
    L.append(_center_block(COMPASS_ROSE))
    L.append("")
    for line in directions_lines(picks, located):
        for w in _wrap("> " + line):
            L.append(w)
        L.append("")
    L.append(_rule("="))
    L.append(_center("there's a spot"))
    L.append(_center("in the shell for you"))
    L.append("")
    return "\n".join(L)


def print_or_preview(text, host=None):
    """Print to the network or USB printer; fall back to a preview file. Returns a status dict.

    host overrides ESCPOS_HOST so a station can be bound to its own printer.
    """
    host = host or os.environ.get("ESCPOS_HOST")
    vid = os.environ.get("ESCPOS_VENDOR_ID")
    pid = os.environ.get("ESCPOS_PRODUCT_ID")
    if host:
        try:
            from escpos.printer import Network  # requires: pip install python-escpos
            p = Network(host, port=int(os.environ.get("ESCPOS_PORT", "9100")),
                        timeout=10, profile=PROFILE)
            p.text(text + "\n")
            p.cut()
            p.close()
            return {"status": "printed", "target": f"net {host}"}
        except Exception as e:  # noqa: BLE001
            preview = _save_preview(text)
            return {"status": "preview", "path": preview, "error": f"printer error: {e}"}
    if vid and pid:
        try:
            from escpos.printer import Usb  # requires: pip install python-escpos pyusb
            p = Usb(int(vid, 16), int(pid, 16), profile=PROFILE)
            p.text(text + "\n")
            p.cut()
            return {"status": "printed", "target": f"usb {vid}:{pid}"}
        except Exception as e:  # noqa: BLE001
            preview = _save_preview(text)
            return {"status": "preview", "path": preview, "error": f"printer error: {e}"}
    preview = _save_preview(text)
    return {"status": "preview", "path": preview,
            "note": "No ESCPOS_HOST or ESCPOS_VENDOR_ID/PRODUCT_ID set — saved a preview "
                    "instead of printing."}


def _save_preview(text):
    os.makedirs(RECEIPTS, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = os.path.join(RECEIPTS, f"receipt-{stamp}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    with open(os.path.join(RECEIPTS, "latest.txt"), "w", encoding="utf-8") as f:
        f.write(text)
    return path

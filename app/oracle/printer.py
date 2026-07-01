"""Thermal receipt: format the reading + quest for a 58mm ESC/POS printer.

Prints to a USB ESC/POS printer if python-escpos is installed and ESCPOS_VENDOR_ID /
ESCPOS_PRODUCT_ID are set; otherwise saves a text preview to app/receipts/ so you can see
exactly what would print. 58mm printers are ~32 characters wide.
"""
import os
import textwrap
import time

from .deck import REPO
from .geo import COMPASS_ROSE, directions_lines

WIDTH = 32
RECEIPTS = os.path.join(REPO, "app", "receipts")


def _rule(ch="-"):
    return ch * WIDTH


def _center(s):
    return s[:WIDTH].center(WIDTH)


def _wrap(s):
    return textwrap.wrap(s, WIDTH) or [""]


def format_receipt(payload, picks, located):
    L = []
    L.append(_center("* THE TERRIBLE TURTLE *"))
    L.append(_center("ORACLE"))
    L.append(_center("Move Slow & Bite Things"))
    L.append(_rule("="))
    L.append(time.strftime("%a %b %d  %H:%M"))
    L.append("")
    L.append("YOU ASKED:")
    L.extend(_wrap(payload["question"]))
    L.append("")
    L.append(_rule())
    L.append("THE TREE DREW:")
    labels = {"roots": "FACE", "trunk": "STAND", "branches": "REACH"}
    for realm in ("roots", "trunk", "branches"):
        c = picks[realm]
        L.append(f"[{labels[realm]}] {c['name']}")
    L.append(_rule())
    L.append("")
    L.append("THE READING")
    L.extend(_wrap(payload["reading"]))
    L.append("")
    L.append("YOUR QUEST")
    L.extend(_wrap(payload["adventure"]))
    L.append("")
    L.append(_rule())
    L.append("WHERE TO GO")
    L.append(COMPASS_ROSE)
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


def print_or_preview(text):
    """Try the USB printer; fall back to saving a preview file. Returns a status dict."""
    vid = os.environ.get("ESCPOS_VENDOR_ID")
    pid = os.environ.get("ESCPOS_PRODUCT_ID")
    if vid and pid:
        try:
            from escpos.printer import Usb  # requires: pip install python-escpos pyusb
            p = Usb(int(vid, 16), int(pid, 16), profile="TM-T88III")
            p.text(text + "\n")
            p.cut()
            return {"status": "printed", "target": f"usb {vid}:{pid}"}
        except Exception as e:  # noqa: BLE001
            preview = _save_preview(text)
            return {"status": "preview", "path": preview, "error": f"printer error: {e}"}
    preview = _save_preview(text)
    return {"status": "preview", "path": preview,
            "note": "No ESCPOS_VENDOR_ID/PRODUCT_ID set — saved a preview instead of printing."}


def _save_preview(text):
    os.makedirs(RECEIPTS, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = os.path.join(RECEIPTS, f"receipt-{stamp}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    with open(os.path.join(RECEIPTS, "latest.txt"), "w", encoding="utf-8") as f:
        f.write(text)
    return path

"""Generate web-optimized card images: cards/web/thumb (300px) + cards/web/med (900px)."""
from PIL import Image
import json, os
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ART = f"{REPO}/cards/art"
os.makedirs(f"{REPO}/cards/web/thumb", exist_ok=True); os.makedirs(f"{REPO}/cards/web/med", exist_ok=True)
d = json.load(open(f"{REPO}/data/cards.json"))
def save(src, dst, w, q=82):
    im = Image.open(src).convert("RGB"); h = int(w*im.size[1]/im.size[0])
    im.resize((w, h), Image.LANCZOS).save(dst, "JPEG", quality=q, optimize=True)
for c in d["cards"]:
    save(f"{ART}/{c['id']}.png", f"{REPO}/cards/web/thumb/{c['id']}.jpg", 300)
    save(f"{ART}/{c['id']}.png", f"{REPO}/cards/web/med/{c['id']}.jpg", 900)
save(f"{REPO}/cards/back.png", f"{REPO}/cards/web/med/back.jpg", 900)
print("web images generated")

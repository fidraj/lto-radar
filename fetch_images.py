#!/usr/bin/env python3
"""Download product images listed in a mapping JSON and wire them into data.json.

Usage: python3 fetch_images.py mapping1.json [mapping2.json ...]
Mapping format: [{"chain": "...", "item": "...", "imageUrl": "https://..." | null}]
Items are matched to data.json by exact (chain, item) or by fuzzy prefix match.
Images are resized to 640px wide JPEGs via sips (macOS) into images/.
"""
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).parent
IMAGES = ROOT / "images"
IMAGES.mkdir(exist_ok=True)


def slug(chain, item):
    s = re.sub(r"[^a-z0-9]+", "-", f"{chain}-{item}".lower()).strip("-")
    return s[:80]


def find_item(items, chain, name):
    for p in items:
        if p["chain"] == chain and p["item"] == name:
            return p
    low = name.lower()[:30]
    for p in items:
        if p["chain"] == chain and (p["item"].lower().startswith(low) or low in p["item"].lower()):
            return p
    return None


def fetch(url, dest):
    raw = dest.with_suffix(".raw")
    r = subprocess.run(
        ["curl", "-sSLf", "--max-time", "30", "-A", "Mozilla/5.0 (Macintosh)", "-o", str(raw), url],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        print(f"  download failed: {url} ({r.stderr.strip()[:100]})")
        return False
    kind = subprocess.run(["file", "-b", "--mime-type", str(raw)], capture_output=True, text=True).stdout.strip()
    if not kind.startswith("image/"):
        print(f"  not an image ({kind}): {url}")
        raw.unlink(missing_ok=True)
        return False
    if not convert(raw, dest):
        print(f"  convert failed: {url}")
        raw.unlink(missing_ok=True)
        return False
    raw.unlink(missing_ok=True)
    return True


def convert(raw, dest):
    """Resize to 640px-wide JPEG: Pillow if available, else sips (macOS), else keep as-is."""
    try:
        from PIL import Image
        img = Image.open(raw).convert("RGB")
        if img.width > 640:
            img = img.resize((640, round(img.height * 640 / img.width)), Image.Resampling.LANCZOS)
        img.save(dest, "JPEG", quality=72)
        return True
    except ImportError:
        pass
    except Exception:
        return False
    r = subprocess.run(
        ["sips", "-s", "format", "jpeg", "-s", "formatOptions", "72",
         "--resampleWidth", "640", str(raw), "--out", str(dest)],
        capture_output=True, text=True,
    )
    if r.returncode == 0 and dest.exists():
        return True
    # last resort: keep the original bytes (page renders any image type fine)
    dest.write_bytes(raw.read_bytes())
    return True


def main():
    data = json.loads((ROOT / "data.json").read_text())
    items = data["items"]
    ok = missed = 0

    for path in sys.argv[1:]:
        for row in json.loads(pathlib.Path(path).read_text()):
            if not row.get("imageUrl"):
                continue
            p = find_item(items, row["chain"], row["item"])
            if not p:
                print(f"  no data.json match: {row['chain']} / {row['item']}")
                missed += 1
                continue
            dest = IMAGES / (slug(p["chain"], p["item"]) + ".jpg")
            if fetch(row["imageUrl"], dest):
                p["image"] = dest.name
                ok += 1
            else:
                missed += 1

    (ROOT / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"images: {ok} saved, {missed} failed/unmatched")


if __name__ == "__main__":
    main()

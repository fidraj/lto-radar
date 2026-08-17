#!/usr/bin/env python3
"""Download product images and wire them into data.json.

Usage:
  python3 fetch_images.py                    # process "imageUrl" fields in data.json itself
  python3 fetch_images.py mapping.json ...   # process mapping files (legacy local mode)

With no arguments, every data.json item that has an "imageUrl" but no "image" is
downloaded — this is the mode the fetch-images GitHub Action runs after each push.
Mapping format: [{"chain": "...", "item": "...", "imageUrl": "https://..." | null}]
Items are matched to data.json by exact (chain, item) or by fuzzy prefix match.
Images are resized to 640px wide JPEGs (Pillow, or sips on macOS) into images/.
"""
import html
import json
import pathlib
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

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


UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# article heroes that are never a product shot
JUNK = ("logo", "placeholder", "fallback", "favicon", "sprite", "avatar", "default-", "/icon")


def og_image(page_url):
    """Pull the og:image out of a news/press page - it is the official press photo."""
    if not page_url:
        return None
    out = subprocess.run(["curl", "-sSL", "--max-time", "25", "-A", UA, page_url],
                         capture_output=True, text=True, errors="ignore").stdout
    for pat in (r'og:image["\'][^>]*content=["\']([^"\']+)',
                r'content=["\']([^"\']+)["\'][^>]*og:image',
                r'name=["\']twitter:image["\'][^>]*content=["\']([^"\']+)'):
        m = re.search(pat, out, re.I)
        if not m:
            continue
        url = html.unescape(m.group(1)).strip()
        if url.startswith("//"):
            url = "https:" + url
        if url.startswith("http") and not any(j in url.lower() for j in JUNK):
            return url
    return None


# words that say nothing about which product this is
STOP = {"new", "the", "and", "with", "for", "returning", "return", "limited", "time",
        "deal", "deals", "menu", "meal", "meals", "free", "app", "exclusive", "only",
        "back", "leaked", "unconfirmed", "rumored", "expected", "regional", "test",
        "lineup", "collection", "edition", "featuring", "value", "promo", "promotion"}


def relevant(url, item_name):
    """An article hero is only trustworthy if it actually names the product.

    Press pages happily serve a logo, a storefront or last week's launch photo as
    og:image; requiring a distinctive word from the item name to appear in the
    image URL is what separates the real product shot from those.
    """
    toks = {t for t in re.split(r"[^a-z0-9]+", item_name.lower()) if len(t) >= 4 and t not in STOP}
    low = url.lower()
    return any(t in low for t in toks)


def good_enough(path):
    """Reject tiny crops, banners and icons that slipped through."""
    if path.stat().st_size < 8000:
        return False
    try:
        from PIL import Image
        w, h = Image.open(path).size
        return w >= 400 and h >= 200
    except ImportError:
        return True
    except Exception:
        return False


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
    if not good_enough(raw):
        print(f"  too small / not a product shot: {url}")
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


def gather(items, paths):
    """Yield (url, item-or-None, label, auto) from mapping files, or from data.json itself.

    In data.json mode an item's own "imageUrl" wins; when it has none (the daily
    refresh agent does not always find one) the image is derived from the item's
    source article, so the board fills in without depending on the agent.
    """
    if paths:
        for path in paths:
            for row in json.loads(pathlib.Path(path).read_text()):
                if row.get("imageUrl"):
                    yield row["imageUrl"], find_item(items, row["chain"], row["item"]), f"{row['chain']} / {row['item']}", False
        return

    todo = [p for p in items if not p.get("image")]
    for p in todo:
        if p.get("imageUrl"):
            yield p["imageUrl"], p, f"{p['chain']} / {p['item']}", False

    needs_og = [p for p in todo if not p.get("imageUrl") and p.get("source")]
    if not needs_og:
        return
    print(f"deriving images from source articles for {len(needs_og)} item(s)...")
    with ThreadPoolExecutor(max_workers=8) as ex:
        derived = list(ex.map(lambda p: og_image(p["source"]), needs_og))
    for p, url in zip(needs_og, derived):
        if url and relevant(url, p["item"]):
            yield url, p, f"{p['chain']} / {p['item']}", True


def main():
    data = json.loads((ROOT / "data.json").read_text())
    items = data["items"]
    ok = missed = 0

    for url, p, label, auto in gather(items, sys.argv[1:]):
        if not p:
            print(f"  no data.json match: {label}")
            missed += 1
            continue
        dest = IMAGES / (slug(p["chain"], p["item"]) + ".jpg")
        if fetch(url, dest):
            p["image"] = dest.name
            if auto:
                # flag for review: derived from the article hero, not hand-picked
                p["imageAuto"] = True
                print(f"  auto: {label}")
            ok += 1
        else:
            missed += 1

    (ROOT / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(f"images: {ok} saved, {missed} failed/unmatched")


if __name__ == "__main__":
    main()

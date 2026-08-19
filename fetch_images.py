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
import datetime
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
DEAD = set()   # source URLs that look gone, reported at the end of the run

JUNK = ("logo", "placeholder", "fallback", "favicon", "sprite", "avatar", "default-", "/icon")


def published_year(page_url):
    """The year the source article was published, if the page states it."""
    out = subprocess.run(
        ["curl", "-sSL", "--max-time", "20", "--proto", "=http,https",
         "--proto-redir", "=http,https", "--max-filesize", "10000000", "-A", UA, page_url],
        capture_output=True, text=True, errors="ignore").stdout
    for pat in (r'article:published_time["\'][^>]*content=["\'](\d{4})',
                r'"datePublished"\s*:\s*["\'](\d{4})',
                r'<time[^>]+datetime=["\'](\d{4})'):
        m = re.search(pat, out, re.I)
        if m:
            return m.group(1)
    return None


def check_years(items):
    """Flag items whose start year disagrees with the year their source was published.

    The refresh agent has repeatedly written this year onto a promo announced in a
    previous one (a Dec 2025 SpongeBob menu filed as Dec 2026), which puts a long-dead
    promo on the board. Only recent/future items are checked - old ones cost fetches
    and no longer matter.
    """
    import datetime
    cutoff = str(datetime.date.today() - datetime.timedelta(days=45))
    recent = [p for p in items
              if p.get("source") and (p.get("startDate") or "") >= cutoff]
    if not recent:
        return
    with ThreadPoolExecutor(max_workers=8) as ex:
        years = list(ex.map(lambda p: published_year(p["source"]), recent))
    for p, y in zip(recent, years):
        if y and y != p["startDate"][:4]:
            print(f"  WARNING: starts {p['startDate']} but source was published in {y}: "
                  f"{p['chain']} / {p['item'][:44]}")


def page_images(page_url):
    """Every plausible product photo on a page, best candidate first.

    og:image alone is unreliable - press pages serve logos, storefronts and last
    month's launch as their social card - so scan the whole page and rank what we
    find. Only URLs already present in data.json are ever fetched.
    """
    if not page_url:
        return []
    raw = subprocess.run(
        ["curl", "-sSL", "--max-time", "25", "--proto", "=http,https",
         "--proto-redir", "=http,https", "--max-filesize", "10000000", "-A", UA,
         "-w", "\n<<<META>>>%{url_effective}\t%{http_code}", page_url],
        capture_output=True, text=True, errors="ignore").stdout
    html_src, _, meta = raw.rpartition("<<<META>>>")
    final, _, code = meta.partition("\t")

    # A source that 404s, or that bounces to the site's front page, is a dead link -
    # worth surfacing because a promo with no checkable source is worth little.
    # Note 403/503 are NOT dead: many press sites (Starbucks, BusinessWire, QSR)
    # serve a bot challenge to CI while working fine in a browser.
    # only hard evidence: a 404/410, or a 200 that silently bounced to the site root
    # (AOL does this with deleted articles). A short body means a bot challenge, not
    # a dead page, so it must not count.
    bounced = (code.strip() == "200"
               and final.rstrip("/").count("/") <= 2
               and page_url.rstrip("/").count("/") > 2)
    if code.strip() in ("404", "410") or bounced:
        DEAD.add(page_url)

    found, seen = [], set()

    def add(raw, social, alt=""):
        if not raw:
            return
        url = html.unescape(raw.strip()).split(" ")[0]
        if url.startswith("//"):
            url = "https:" + url
        elif url.startswith("/"):
            m = re.match(r"(https?://[^/]+)", page_url)
            url = (m.group(1) + url) if m else ""
        if not url.startswith("http") or url in seen:
            return
        if any(j in url.lower() for j in JUNK):
            return
        if not re.search(r"\.(jpe?g|png|webp)(\?|$)", url, re.I) and not social:
            return
        seen.add(url)
        found.append((url, social, alt))

    for pat in (r'og:image["\'][^>]*content=["\']([^"\']+)',
                r'content=["\']([^"\']+)["\'][^>]*og:image',
                r'name=["\']twitter:image["\'][^>]*content=["\']([^"\']+)'):
        for m in re.finditer(pat, html_src, re.I):
            add(m.group(1), True)
    for tag in re.finditer(r'<img[^>]+>', html_src, re.I):
        t = tag.group(0)
        alt = (re.search(r'alt=["\']([^"\']*)', t, re.I) or [None, ""])[1]
        for attr in ("src", "data-src", "data-lazy-src"):
            m = re.search(attr + r'=["\']([^"\']+)', t, re.I)
            if m:
                add(m.group(1), False, alt)
        m = re.search(r'srcset=["\']([^"\',\s]+)', t, re.I)
        if m:
            add(m.group(1), False, alt)

    def rank(item):
        url, social, _alt = item
        low = url.lower()
        score = 0
        if any(cdn in low for cdn in ("prnewswire", "businesswire", "/wp-content/uploads/",
                                      "restaurantnews", "blogger.googleusercontent")):
            score -= 2                       # press/editorial photo hosts
        if social:
            score -= 1                       # the page's chosen hero
        dims = re.search(r"[/_-](?:w)?(\d{2,4})[x-](?:h)?(\d{2,4})", low)
        if dims and (int(dims.group(1)) < 300 or int(dims.group(2)) < 200):
            score += 3                       # a thumbnail, not the real photo
        return score

    return [(u, alt) for u, _, alt in sorted(found, key=rank)]


# words that say nothing about which product this is
STOP = {"new", "the", "and", "with", "for", "returning", "return", "limited", "time",
        "deal", "deals", "menu", "meal", "meals", "free", "app", "exclusive", "only",
        "back", "leaked", "unconfirmed", "rumored", "expected", "regional", "test",
        "lineup", "collection", "edition", "featuring", "value", "promo", "promotion"}


def relevant(url, item_name, alt=""):
    """A photo is only trustworthy if its URL actually names the product.

    Pages happily serve a logo, a storefront or last week's launch photo; requiring
    a distinctive word from the item name in the image URL is what separates the
    real product shot from those.
    """
    toks = {t for t in re.split(r"[^a-z0-9]+", item_name.lower()) if len(t) >= 4 and t not in STOP}
    hay = (url + " " + (alt or "")).lower()
    return any(t in hay for t in toks)


def ended(p):
    """True once a promo's end date has passed."""
    e = p.get("endDate")
    return bool(e and len(e) == 10 and e[:4].isdigit()
                and e < str(datetime.date.today()))


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
        ["curl", "-sSLf", "--max-time", "30", "--proto", "=http,https",
         "--proto-redir", "=http,https", "--max-filesize", "25000000",
         "-A", "Mozilla/5.0 (Macintosh)", "-o", str(raw), url],
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

    # promos that are already over are off the board, so sourcing photos (and
    # fetching their pages) for them is wasted work
    todo = [p for p in items if not p.get("image") and not ended(p)]
    for p in todo:
        if p.get("imageUrl"):
            yield [p["imageUrl"]], p, f"{p['chain']} / {p['item']}", False

    # imageSkip marks an item a human reviewed and rejected the auto image for -
    # without it, every run happily re-derives the same wrong picture
    needs = [p for p in todo
             if not p.get("imageUrl") and p.get("source") and not p.get("imageSkip")]
    if not needs:
        return
    print(f"scanning source articles for {len(needs)} item(s)...")
    with ThreadPoolExecutor(max_workers=8) as ex:
        pages = list(ex.map(lambda p: page_images(p["source"]), needs))
    for p, cands in zip(needs, pages):
        good = [u for u, alt in cands if relevant(u, p["item"], alt)]
        if good:
            yield good, p, f"{p['chain']} / {p['item']}", True


def main():
    data = json.loads((ROOT / "data.json").read_text())
    items = data["items"]
    ok = missed = 0

    used = set()
    for urls, p, label, auto in gather(items, sys.argv[1:]):
        if not p:
            print(f"  no data.json match: {label}")
            missed += 1
            continue
        dest = IMAGES / (slug(p["chain"], p["item"]) + ".jpg")
        got = False
        for url in urls:
            # one photo standing in for several items is nearly always the wrong photo
            if auto and url in used:
                continue
            if fetch(url, dest):
                p["image"] = dest.name
                used.add(url)
                if auto:
                    p["imageAuto"] = True   # flag for review: taken from the article, not hand-picked
                    print(f"  auto: {label}")
                ok += 1
                got = True
                break
        if not got:
            missed += 1

    # a promo dated far in the future is nearly always a source article whose year
    # was misread (a Dec 2025 press release recorded as Dec 2026)
    import datetime
    today = datetime.date.today()
    if DEAD:
        for p in items:
            if p.get("source") in DEAD:
                print(f"  WARNING: source looks dead: {p['chain']} / {p['item'][:46]}  {p['source'][:70]}")

    # aggregators delete their articles and expose no publication date, so the year
    # check above is blind to them - flag them so they get replaced with a stable source
    AGGREGATORS = ("msn.com", "aol.com", "yahoo.com", "trendhunter.com", "lipstickalley.com",
                   "dealnews.com", "slickdeals.net", "foodchainhub.com")
    for p in items:
        src = (p.get("source") or "").lower()
        if any(a in src for a in AGGREGATORS) and not ended(p):
            print(f"  WARNING: unstable source, replace it: {p['chain']} / {p['item'][:44]}  {src[:56]}")

    check_years(items)

    far = [p for p in items
           if (p.get("startDate") or "").count("-") == 2
           and p["startDate"] > str(today + datetime.timedelta(days=90))]
    for p in far:
        print(f"  WARNING: starts {p['startDate']}, check the source year: {p['chain']} / {p['item'][:50]}")

    (ROOT / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(f"images: {ok} saved, {missed} failed/unmatched")


if __name__ == "__main__":
    main()

# Daily data refresh playbook

You are refreshing **LTO Radar**, a tracker of limited-time offers (LTOs) at US fast-food
chains. This repo is a static site served by GitHub Pages: `index.html` renders `data.json`
at runtime. Your job is to bring `data.json` and `images/` up to date, then commit and push
to `main`. Do NOT redesign or edit `index.html` unless it is broken.

## Chains to cover (all of them, every run)

McDonald's, Burger King, Wendy's, Taco Bell, Starbucks, KFC, Chick-fil-A, Dunkin', Krispy Kreme,
Sonic, Arby's, Jack in the Box, Dairy Queen, Popeyes, Wingstop, Raising Cane's, Zaxby's,
Chipotle, Pizza Hut, Domino's, Subway.

## Research rules — completeness is the top priority

A promo was once missed because research relied on news search alone. Never repeat that.
For EVERY chain do BOTH:

1. **Fetch the chain's official promo/newsroom index** and enumerate everything listed:
   - https://www.krispykreme.com/promos
   - https://news.dunkindonuts.com/news
   - https://corporate.mcdonalds.com/corpmcd/our-stories.html
   - https://news.bk.com/blog-posts
   - https://www.wendys.com/blog and https://www.wendys.com/offers
   - https://www.tacobell.com/news
   - https://about.starbucks.com/press/
   - https://global.kfc.com/press-releases/ and KFC US news coverage
   - https://www.chick-fil-a.com/press-room
   - https://www.sonicdrivein.com/menu (plus Sonic news coverage)
   - https://arbys.com/menu (plus Arby's news coverage)
   - https://www.jackinthebox.com/food (plus press coverage)
   - https://www.dairyqueen.com/en-us/blizzard-of-the-month/ and DQ news
   - https://www.popeyes.com/menu (plus press coverage)
   - https://www.wingstop.com/menu and Wingstop news
   - https://www.raisingcanes.com/news
   - https://www.zaxbys.com/news
   - https://newsroom.chipotle.com/
   - https://blog.pizzahut.com/ and Pizza Hut press coverage
   - https://ir.dominos.com/news-releases and Domino's menu news
   - https://newsroom.subway.com/
2. **Web-search** for "<chain> new menu item <current month/year>", "<chain> limited time offer",
   and food-news roundups (brandeating.com, chewboom.com, fastfoodpost.com).

## Updating data.json

Schema per item:
```json
{
  "chain": "...", "item": "...", "description": "...",
  "category": "burger|sandwich|taco|drink|dessert|donut|chicken|food|event",
  "startDate": "YYYY-MM-DD or null",
  "endDate": "YYYY-MM-DD or 'while supplies last' or null",
  "status": "active|upcoming|ending-soon",
  "source": "url",
  "image": "filename-in-images-dir.jpg or null"
}
```

- **Add** newly found offers (including short flash drops and rewards/value deals).
- **Update** existing items whose dates/status changed; fix dates when chains announce exact windows.
- **Keep** ended items in the file (the app hides anything past its endDate automatically);
  they are the historical record. Set their real endDate.
- **Never delete** an item unless it was factually wrong.
- Mark rumored/leaked items clearly in the item name or description ("leaked, unconfirmed").
- Convert vague dates to concrete best-estimate `YYYY-MM-DD`; prefer official dates when known.
- Set the top-level `"researched"` field to today's date (YYYY-MM-DD).

## Images

Your environment CANNOT download files. Do NOT run `fetch_images.py` and do not try to
curl images — a GitHub Action (`fetch-images`) downloads them after you push.

For each NEW item, you MUST make a real attempt to find an official product image and put
its direct URL on the item:

```json
"imageUrl": "https://.../product.jpg", "image": null
```

How to find one (do this per new item — do not skip straight to null):

1. Fetch the item's own `source` article and read its `og:image` meta tag. Food-news sites
   (brandeating.com, fastfoodpost.com, chewboom.com, restaurantnews.com) republish the
   chain's official press photo as the article hero, and their images are directly linkable.
2. If the source has no usable image, check the chain's press release on PRNewswire /
   BusinessWire — their `mma.prnewswire.com` / `mms.businesswire.com` media URLs are direct
   image links.
3. Verify the URL really is that product's photo: it should end in .jpg/.png/.webp (or be a
   known image CDN) and its filename/context should match the item. Reject site logos,
   storefront photos, unrelated products, and article-header collages.

Rules:
- Never use watermarked images or a photo of a different product.
- An official campaign/promo graphic is fine for value menus and deal promos.
- Only use `null` when you genuinely could not find an official image (common for leaked or
  unconfirmed items) — `null` for everything is a failed run, not a safe default.
- Some chains (notably about.starbucks.com) block automated fetching; for those, get the
  image from a food-news republish instead.
- Leave existing items' `image` fields alone.

After your push, the Action downloads every item that has an `imageUrl` but no `image`,
resizes it into `images/`, fills in the `image` filename, and commits. Until that lands,
the site renders `imageUrl` directly, so nothing looks broken in between.

## Validate before pushing

```
python3 -c "import json; d=json.load(open('data.json')); assert d['items'], 'empty'; print(len(d['items']), 'items OK')"
```

Also sanity-check: every item has chain/item/description/status; every new item either has
an `imageUrl` or intentionally has none.

## Commit and push

```
git add data.json
git commit -m "data refresh <YYYY-MM-DD>"
git push origin main
```

GitHub Pages redeploys automatically, and the fetch-images Action fills in images in a
follow-up commit. Done.

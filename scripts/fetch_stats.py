#!/usr/bin/env python3
"""Collect per-post view counts for Uswah's social accounts.

Each platform runs only when its settings are present (environment variables),
and a failure in one platform never stops the others. Results are merged into
data/stats.json, and the same data is embedded into uswah.html so the page also
works when opened as a single file.

Settings (all optional):
  YOUTUBE_API_KEY, YOUTUBE_CHANNEL          e.g. "@uswah" or "UCxxxx"
  TELEGRAM_CHANNEL                          public channel username, e.g. "uswah"
  TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET, TIKTOK_REFRESH_TOKEN
  X_BEARER_TOKEN, X_USERNAME
  X_WINDOW_DAYS                             days of X posts re-read on each run after the first (default 10)
  START_DATE                                first day to count (default: "since" in data/stats.json, 2026-08-27)

Standard library only: no pip install needed.
"""
import csv
import datetime as dt
import io
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "stats.json"
PAGE = ROOT / "uswah.html"
UA = "Mozilla/5.0 (compatible; UswahStats/1.0)"



def env(name):
    return (os.environ.get(name) or "").strip()


def _since():
    """Start of counting: START_DATE env, else "since" in data/stats.json, else 2026-08-27."""
    if env("START_DATE"):
        return env("START_DATE")
    try:
        return json.loads(DATA.read_text(encoding="utf-8")).get("since") or "2026-08-27"
    except (OSError, ValueError):
        return "2026-08-27"


SINCE = _since()


def http(url, *, data=None, headers=None, method=None):
    body = None
    if data is not None:
        body = data if isinstance(data, bytes) else json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, method=method, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


def http_json(url, **kw):
    return json.loads(http(url, **kw))


# --------------------------------------------------------------------------- YouTube
def iso_seconds(d):
    """PT1M5S -> 65"""
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", d or "")
    if not m:
        return 0
    days, h, mi, sec = (int(x or 0) for x in m.groups())
    return days * 86400 + h * 3600 + mi * 60 + sec


def fetch_youtube():
    key, channel = env("YOUTUBE_API_KEY"), env("YOUTUBE_CHANNEL")
    if not (key and channel):
        return None
    api = "https://www.googleapis.com/youtube/v3/"

    def call(path, **params):
        params["key"] = key
        return http_json(api + path + "?" + urllib.parse.urlencode(params))

    if channel.startswith("UC"):
        ch = call("channels", part="contentDetails", id=channel)
    else:
        ch = call("channels", part="contentDetails", forHandle=channel if channel.startswith("@") else "@" + channel)
    if not ch.get("items"):
        # Help to find the right identifier: list the closest channels by name.
        found = call("search", part="snippet", type="channel", maxResults=5, q=channel.lstrip("@"))
        names = "; ".join(f'{i["snippet"]["channelTitle"]} ({i["snippet"]["channelId"]})' for i in found.get("items", []))
        raise RuntimeError(f"channel '{channel}' not found. Closest matches: {names or 'none'}")
    uploads = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

    ids, token = [], ""
    while True:
        params = dict(part="contentDetails", playlistId=uploads, maxResults=50)
        if token:
            params["pageToken"] = token
        pl = call("playlistItems", **params)
        ids += [i["contentDetails"]["videoId"] for i in pl["items"]]
        token = pl.get("nextPageToken", "")
        if not token or len(ids) >= 1000:
            break

    posts = []
    for i in range(0, len(ids), 50):
        v = call("videos", part="snippet,statistics,contentDetails", id=",".join(ids[i:i + 50]))
        for it in v["items"]:
            date = it["snippet"]["publishedAt"][:10]
            if date < SINCE:
                continue
            seconds = iso_seconds(it.get("contentDetails", {}).get("duration"))
            is_short = 0 < seconds <= 180 or "#shorts" in it["snippet"]["title"].lower()
            posts.append({
                "platform": "youtube", "id": it["id"], "date": date,
                "title": it["snippet"]["title"], "views": int(it["statistics"].get("viewCount", 0)),
                "url": f"https://www.youtube.com/{'shorts' if is_short else 'watch?v='}{'/' if is_short else ''}{it['id']}",
                "kind": "short" if is_short else "video",
            })
    return posts


# --------------------------------------------------------------------------- Telegram
def parse_tg_count(s):
    s = s.strip().upper().replace(",", "")
    mult = 1
    if s.endswith("K"):
        mult, s = 1_000, s[:-1]
    elif s.endswith("M"):
        mult, s = 1_000_000, s[:-1]
    return int(round(float(s) * mult))


# Telegram post types, decided from the channel's approved hashtags and wording.
CATEGORY_LABELS = {
    "shamail": "مقاطع الشمائل",
    "quotes": "الاقتباسات",
    "audio": "الكتب والمنظومات الصوتية",
    "salawat": "تصاميم الصلاة على النبي ﷺ",
    "intro": "الفيديو التعريفي",
    "other": "منشورات أخرى",
    "announcement": "إعلانات (غير محتسبة)",
}
FULL_TEXT = {}  # post id -> full text, for log output only (not stored)


def media_kind(block):
    if "tgme_widget_message_video" in block or "tgme_widget_message_roundvideo" in block:
        return "video"
    if "tgme_widget_message_photo_wrap" in block:
        return "photo"
    if "tgme_widget_message_voice" in block or "tgme_widget_message_document" in block:
        return "file"
    return "text"
AUDIO_MARKERS = ("#كتاب_صوتي", "#كتب_صوتية", "#منظومات", "كتاب صوتي", "كتبنا الصوتية", "الكتب الصوتية",
                 "منظومة", "قصيدة", "القصيدة", "#دار_الحبيب")


def classify(text):
    t = text or ""
    if "#اقتباسات_أسوة" in t:
        return "quotes"
    if any(m in t for m in AUDIO_MARKERS):
        return "audio"
    body = re.sub(r"#\S+", "", t).strip(" …·-")
    if "#صلى_الله_عليه_وسلم" in t and len(body) < 12:
        return "salawat"
    if "الشمائل" in t:
        return "shamail"
    return "other"


IMAGE_URL = {}  # post id -> remote image / video-thumbnail url found in this run
IMG_DIR = ROOT / "assets" / "designs"
SHOWCASE = {"salawat": 4, "quotes": 4, "shamail": 4}  # designs kept per type: the most viewed


def image_url(block):
    m = re.search(r"tgme_widget_message_(?:photo_wrap|video_thumb)[^>]*?background-image:url\('([^']+)'\)", block, re.S)
    return html.unescape(m.group(1)) if m else ""


def http_bytes(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def image_ext(b):
    if b[:3] == b"\xff\xd8\xff":
        return "jpg"
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "webp"
    return "jpg"


def image_ratio(b):
    """width / height for JPEG and PNG; 1.0 when unknown."""
    try:
        if b[:8] == b"\x89PNG\r\n\x1a\n":
            return int.from_bytes(b[16:20], "big") / int.from_bytes(b[20:24], "big")
        if b[:3] == b"\xff\xd8\xff":
            i = 2
            while i < len(b):
                if b[i] != 0xFF:
                    i += 1
                    continue
                marker = b[i + 1]
                if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                    h = int.from_bytes(b[i + 5:i + 7], "big")
                    w = int.from_bytes(b[i + 7:i + 9], "big")
                    return w / h
                i += 2 + int.from_bytes(b[i + 2:i + 4], "big")
    except Exception:
        pass
    return 1.0


def download_showcase(data):
    """Keep local copies of the most viewed designs per type for the home-page gallery."""
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    existing = {f.stem: f for f in IMG_DIR.iterdir() if f.is_file()}
    keep = set()
    for p in data["posts"]:
        p.pop("image", None)
        p.pop("ar", None)
    for cat, n in SHOWCASE.items():
        cands = [p for p in data["posts"] if p["platform"] == "telegram" and p.get("category") == cat
                 and (p["id"] in IMAGE_URL or p["id"] in existing)]
        for p in sorted(cands, key=lambda x: -x["views"])[:n]:
            f = existing.get(p["id"])
            if f is None and p["id"] in IMAGE_URL:
                try:
                    blob = http_bytes(IMAGE_URL[p["id"]])
                    f = IMG_DIR / f"{p['id']}.{image_ext(blob)}"
                    f.write_bytes(blob)
                except Exception as e:
                    print(f"  ! image {p['id']}: {e}", file=sys.stderr)
                    continue
            if f is not None:
                p["image"] = f"assets/designs/{f.name}"
                p["ar"] = round(image_ratio(f.read_bytes()), 4)
                keep.add(f.name)
    for f in IMG_DIR.iterdir():
        if f.is_file() and f.name not in keep:
            f.unlink()
    print(f"  showcase images kept: {len(keep)}")


def fetch_telegram():
    """Reads the public preview (t.me/s/<channel>); works for public channels only."""
    channel = env("TELEGRAM_CHANNEL").lstrip("@")
    if not channel:
        return None
    posts, before = [], None
    for _ in range(60):  # ~20 posts per page
        url = f"https://t.me/s/{channel}" + (f"?before={before}" if before else "")
        page = http(url)
        blocks = re.split(r'(?=<div class="tgme_widget_message_wrap)', page)[1:]
        if not blocks:
            break
        ids = []
        for b in blocks:
            m_id = re.search(r'data-post="[^"/]+/(\d+)"', b)
            m_views = re.search(r'<span class="tgme_widget_message_views">([^<]+)</span>', b)
            m_date = re.search(r'<time[^>]+datetime="([^"]+)"', b)
            if not (m_id and m_views and m_date):
                continue
            ids.append(int(m_id.group(1)))
            date = m_date.group(1)[:10]
            m_text = re.search(r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', b, re.S)
            text = html.unescape(re.sub(r"<[^>]+>", " ", m_text.group(1))) if m_text else ""
            text = re.sub(r"\s+", " ", text).strip()
            posts.append({
                "platform": "telegram", "id": f"tg-{m_id.group(1)}", "date": date,
                "title": (text[:90] + "…") if len(text) > 90 else (text or "منشور وسائط"),
                "views": parse_tg_count(m_views.group(1)),
                "url": f"https://t.me/{channel}/{m_id.group(1)}",
                "category": classify(text),
                "media": media_kind(b),
            })
            FULL_TEXT[f"tg-{m_id.group(1)}"] = text
            IMAGE_URL[f"tg-{m_id.group(1)}"] = image_url(b)
        if not ids:
            break
        before = min(ids)
        if min(p["date"] for p in posts) < SINCE or before <= 1:
            break
    return [p for p in posts if p["date"] >= SINCE]


# --------------------------------------------------------------------------- TikTok
def fetch_tiktok():
    ck, cs, rt = env("TIKTOK_CLIENT_KEY"), env("TIKTOK_CLIENT_SECRET"), env("TIKTOK_REFRESH_TOKEN")
    if not (ck and cs and rt):
        return None
    tok = http_json(
        "https://open.tiktokapis.com/v2/oauth/token/",
        data=urllib.parse.urlencode({"client_key": ck, "client_secret": cs, "grant_type": "refresh_token", "refresh_token": rt}).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if "access_token" not in tok:
        raise RuntimeError(f"token refresh failed: {tok}")
    if tok.get("refresh_token") and tok["refresh_token"] != rt:
        print("  ! TikTok issued a new refresh token; update the TIKTOK_REFRESH_TOKEN secret.", file=sys.stderr)

    posts, cursor = [], None
    fields = "id,title,video_description,create_time,view_count,share_url"
    while True:
        body = {"max_count": 20}
        if cursor:
            body["cursor"] = cursor
        r = http_json(
            "https://open.tiktokapis.com/v2/video/list/?fields=" + fields,
            data=body, headers={"Authorization": f"Bearer {tok['access_token']}", "Content-Type": "application/json"},
        )
        d = r.get("data", {})
        for v in d.get("videos", []):
            date = dt.datetime.fromtimestamp(v["create_time"], dt.timezone.utc).date().isoformat()
            posts.append({
                "platform": "tiktok", "id": v["id"], "date": date,
                "title": (v.get("title") or v.get("video_description") or "مقطع تيك توك")[:90],
                "views": int(v.get("view_count", 0)), "url": v.get("share_url", ""),
            })
        cursor = d.get("cursor")
        if not d.get("has_more") or (posts and min(p["date"] for p in posts) < SINCE):
            break
    return [p for p in posts if p["date"] >= SINCE]


# --------------------------------------------------------------------------- X
X_API = "https://api.x.com/2"
X_USER_ID = ""  # filled after the first successful lookup and cached in data/stats.json


def x_get(path, headers, **params):
    url = f"{X_API}/{path}" + ("?" + urllib.parse.urlencode(params) if params else "")
    try:
        return http_json(url, headers=headers)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        hint = {401: "bearer token rejected", 402: "no credits left on the X developer account", 403: "access not allowed for this plan/app", 429: "rate limited"}.get(e.code, "")
        raise RuntimeError(f"X API {e.code} {hint}: {detail}") from None


def fetch_x(since=None, user_id=""):
    """Own posts with their view counts (public_metrics.impression_count), billed per post read.

    The first run reads everything since the start date; later runs only re-read the last
    few days (views of older posts rarely change), which keeps the monthly cost low.
    """
    global X_USER_ID
    token, user = env("X_BEARER_TOKEN"), env("X_USERNAME").lstrip("@")
    if not (token and user):
        return None
    h = {"Authorization": f"Bearer {token}"}
    uid = user_id or x_get(f"users/by/username/{user}", h)["data"]["id"]
    X_USER_ID = uid
    posts, nxt = [], ""
    start = (since or SINCE) + "T00:00:00Z"
    while True:
        q = {"max_results": 100, "tweet.fields": "created_at,public_metrics", "exclude": "retweets,replies", "start_time": start}
        if nxt:
            q["pagination_token"] = nxt
        r = x_get(f"users/{uid}/tweets", h, **q)
        for t in r.get("data", []):
            posts.append({
                "platform": "x", "id": t["id"], "date": t["created_at"][:10],
                "title": re.sub(r"\s+", " ", t["text"])[:90],
                "views": int(t["public_metrics"].get("impression_count", 0)),
                "url": f"https://x.com/{user}/status/{t['id']}",
            })
        nxt = r.get("meta", {}).get("next_token", "")
        if not nxt:
            break
    return posts


# --------------------------------------------------------------------------- content plan
def _plan_date(s):
    m = re.fullmatch(r"\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*", s or "")
    if not m:
        return ""
    mo, d, y = map(int, m.groups())
    try:
        return dt.date(y, mo, d).isoformat()
    except ValueError:
        return ""


def _plan_kind(title):
    t = title.strip()
    if t.startswith("أسبوع"):
        return "note"
    if "ترويجي" in t:
        return "promo"
    for kind, word in (("teaser", "تشويق"), ("release", "نشر"), ("quote", "اقتباس")):
        if t.startswith(word):
            return kind
    return "item"


def parse_plan(text):
    """Monthly calendar sheet -> flat list of {date, project, title, kind}.

    Layout: a header row names the project columns (they start after the date column),
    then one row per day: [week, weekday, date m/d/yyyy, project cells...].
    """
    projects, items = [], []
    for row in csv.reader(io.StringIO(text)):
        cells = [c.strip() for c in row]
        if len(cells) > 4 and sum(1 for c in cells[3:] if c) >= 3 and not _plan_date(cells[2]):
            projects = [(i, c) for i, c in enumerate(cells) if i >= 3 and c]  # header with project names
            continue
        d = _plan_date(cells[2]) if len(cells) > 2 else ""
        if not d or not projects:
            continue
        for i, name in projects:
            title = re.sub(r"\s+", " ", cells[i]) if i < len(cells) else ""
            if title:
                items.append({"date": d, "project": name, "title": title, "kind": _plan_kind(title)})
    return [n for _, n in projects], items


def fetch_plan(url):
    if not url:
        return None
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as r:
        text = r.read().decode("utf-8-sig")
    names, items = parse_plan(text)
    if not items:
        raise RuntimeError("plan sheet parsed to zero items (layout changed?)")
    items.sort(key=lambda x: (x["date"], names.index(x["project"]) if x["project"] in names else 99))
    return {"updated": dt.date.today().isoformat(), "projects": names, "items": items}


# --------------------------------------------------------------------------- merge & write
def merge(data, platform, fetched):
    """Replace the platform's posts inside the freshly read window; older posts are kept as stored."""
    fresh = {p["id"]: {**p, "source": "api"} for p in fetched}
    # Manual entries inside the window the API now covers would be counted twice.
    covered_from = min((p["date"] for p in fetched), default="9999")

    def superseded(p):
        if p["platform"] != platform:
            return False
        return p["id"] in fresh or p["date"] >= covered_from

    kept = [p for p in data["posts"] if not superseded(p) and p["date"] >= SINCE]
    data["posts"] = kept + list(fresh.values())
    if fetched:
        # Per-post API numbers replace hand-typed account totals for this platform,
        # otherwise the same views would be counted twice or by two different methods.
        data["periods"] = [r for r in data["periods"] if not (r["platform"] == platform and r.get("source") != "api")]


def embed_in_page(data):
    if not PAGE.exists():
        return
    page = PAGE.read_text(encoding="utf-8")
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    new, n = re.subn(
        r'(<script id="seed" type="application/json">)(.*?)(</script>)',
        lambda m: m.group(1) + payload + m.group(3), page, count=1, flags=re.S,
    )
    if n:
        PAGE.write_text(new, encoding="utf-8")
        # index.html is an identical copy so the bare domain (uswah.sa) opens the site directly.
        (ROOT / "index.html").write_text(new, encoding="utf-8")
        # /stats/ opens the statistics view directly (uswah.sa/stats).
        stats_page = new.replace("<head>", "<head>\n<script>window.__ROOT__='../';</script>", 1)
        (ROOT / "stats").mkdir(exist_ok=True)
        (ROOT / "stats" / "index.html").write_text(stats_page, encoding="utf-8")
        # /plan/ opens the content-plan view directly (uswah.sa/plan).
        plan_page = new.replace("<head>", "<head>\n<script>window.__ROOT__='../';window.__PAGE__='plan';</script>", 1)
        (ROOT / "plan").mkdir(exist_ok=True)
        (ROOT / "plan" / "index.html").write_text(plan_page, encoding="utf-8")


def main():
    data = json.loads(DATA.read_text(encoding="utf-8")) if DATA.exists() else {"accounts": {}, "periods": [], "posts": []}
    data.setdefault("posts", [])
    data.setdefault("periods", [])
    # Account names can live in data/stats.json; an environment variable overrides them.
    accounts = data.get("accounts", {})
    for platform, var in (("youtube", "YOUTUBE_CHANNEL"), ("telegram", "TELEGRAM_CHANNEL"), ("x", "X_USERNAME")):
        handle = (accounts.get(platform) or {}).get("handle", "").strip()
        if handle and not env(var):
            os.environ[var] = handle
    changed = False
    x_known = any(p["platform"] == "x" for p in data["posts"])
    x_window = (dt.date.today() - dt.timedelta(days=int(env("X_WINDOW_DAYS") or 10))).isoformat()
    x_fn = lambda: fetch_x(max(SINCE, x_window) if x_known else SINCE, (accounts.get("x") or {}).get("id", ""))
    for platform, fn in (("youtube", fetch_youtube), ("telegram", fetch_telegram), ("tiktok", fetch_tiktok), ("x", x_fn)):
        try:
            fetched = fn()
        except Exception as e:  # keep going with the other platforms
            print(f"✗ {platform}: {e}", file=sys.stderr)
            continue
        if fetched is None:
            print(f"- {platform}: not configured, skipped")
            continue
        merge(data, platform, fetched)
        if platform == "x" and X_USER_ID:
            data.setdefault("accounts", {}).setdefault("x", {})["id"] = X_USER_ID
        changed = True
        shorts = [p for p in fetched if p.get("kind") == "short"]
        extra = f" (incl. {len(shorts)} shorts, {sum(p['views'] for p in shorts):,} views)" if any("kind" in p for p in fetched) else ""
        print(f"✓ {platform}: {len(fetched)} posts, {sum(p['views'] for p in fetched):,} views{extra}")

    # Content plan (public Google Sheet published as CSV; link kept in stats.json -> "plan_url").
    try:
        plan = fetch_plan(env("PLAN_CSV_URL") or data.get("plan_url", ""))
        if plan:
            data["plan"] = plan
            changed = True
            print(f"✓ plan: {len(plan['items'])} items, {len(plan['projects'])} projects")
    except Exception as e:  # keep the last good plan
        print(f"✗ plan: {e}", file=sys.stderr)

    # Categories: fill any missing from the title, then apply manual corrections from stats.json.
    overrides = data.get("category_overrides", {})
    for p in data["posts"]:
        if p["platform"] == "telegram" and "category" not in p:
            p["category"] = classify(p["title"])
        if p["platform"] == "youtube" and "category" not in p:
            p["category"] = classify(p["title"])
        if p["id"] in overrides and overrides[p["id"]] in CATEGORY_LABELS:
            p["category"] = overrides[p["id"]]
    if "--embed-only" not in sys.argv and IMAGE_URL:
        download_showcase(data)
    tg = [p for p in data["posts"] if p["platform"] == "telegram"]
    if tg and "--embed-only" not in sys.argv:
        counts = {k: sum(1 for p in tg if p.get("category") == k) for k in CATEGORY_LABELS}
        print("  telegram categories:", ", ".join(f"{k}={v}" for k, v in counts.items()))
        for p in sorted(tg, key=lambda x: x["date"]):
            full_text = FULL_TEXT.get(p["id"], p["title"])
            print(f"    {p['id']} {p['date']} [{p.get('category')}] ({p.get('media', '?')}) {p['views']:,} | {full_text[:150]}")

    if changed or "--embed-only" in sys.argv:
        if changed:
            data["updated"] = dt.date.today().isoformat()
        data["posts"].sort(key=lambda p: (p["date"], p["platform"]), reverse=True)
        DATA.parent.mkdir(parents=True, exist_ok=True)
        DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        embed_in_page(data)


if __name__ == "__main__":
    main()

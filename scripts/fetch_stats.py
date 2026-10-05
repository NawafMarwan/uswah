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
  LOOKBACK_DAYS                             how far back to collect (default 365)

Standard library only: no pip install needed.
"""
import datetime as dt
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
LOOKBACK = int(os.environ.get("LOOKBACK_DAYS") or 365)
SINCE = (dt.date.today() - dt.timedelta(days=LOOKBACK)).isoformat()


def env(name):
    return (os.environ.get(name) or "").strip()


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
        v = call("videos", part="snippet,statistics", id=",".join(ids[i:i + 50]))
        for it in v["items"]:
            date = it["snippet"]["publishedAt"][:10]
            if date < SINCE:
                continue
            posts.append({
                "platform": "youtube", "id": it["id"], "date": date,
                "title": it["snippet"]["title"], "views": int(it["statistics"].get("viewCount", 0)),
                "url": f"https://www.youtube.com/watch?v={it['id']}",
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
            })
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
def fetch_x():
    token, user = env("X_BEARER_TOKEN"), env("X_USERNAME").lstrip("@")
    if not (token and user):
        return None
    h = {"Authorization": f"Bearer {token}"}
    uid = http_json(f"https://api.twitter.com/2/users/by/username/{user}", headers=h)["data"]["id"]
    posts, nxt = [], ""
    start = SINCE + "T00:00:00Z"
    while True:
        q = {"max_results": 100, "tweet.fields": "created_at,public_metrics", "exclude": "retweets,replies", "start_time": start}
        if nxt:
            q["pagination_token"] = nxt
        r = http_json(f"https://api.twitter.com/2/users/{uid}/tweets?" + urllib.parse.urlencode(q), headers=h)
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


# --------------------------------------------------------------------------- merge & write
def merge(data, platform, fetched):
    """Replace the platform's API posts with fresh ones; keep manual entries untouched."""
    fresh = {p["id"]: {**p, "source": "api"} for p in fetched}
    # Manual entries inside the window the API now covers would be counted twice.
    covered_from = min((p["date"] for p in fetched), default="9999")

    def superseded(p):
        if p["platform"] != platform:
            return False
        return p.get("source") == "api" or p["id"] in fresh or p["date"] >= covered_from

    kept = [p for p in data["posts"] if not superseded(p)]
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
    for platform, fn in (("youtube", fetch_youtube), ("telegram", fetch_telegram), ("tiktok", fetch_tiktok), ("x", fetch_x)):
        try:
            fetched = fn()
        except Exception as e:  # keep going with the other platforms
            print(f"✗ {platform}: {e}", file=sys.stderr)
            continue
        if fetched is None:
            print(f"- {platform}: not configured, skipped")
            continue
        merge(data, platform, fetched)
        changed = True
        print(f"✓ {platform}: {len(fetched)} posts, {sum(p['views'] for p in fetched):,} views")

    if changed or "--embed-only" in sys.argv:
        if changed:
            data["updated"] = dt.date.today().isoformat()
        data["posts"].sort(key=lambda p: (p["date"], p["platform"]), reverse=True)
        DATA.parent.mkdir(parents=True, exist_ok=True)
        DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        embed_in_page(data)


if __name__ == "__main__":
    main()

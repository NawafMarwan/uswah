#!/usr/bin/env python3
"""One-off probe: which FREE, no-login ways of reading view counts from X work from a GitHub runner?

Prints facts only (status codes, field names, numbers). Run via the "Probe X (free options)" workflow.
"""
import json
import re
import sys
import urllib.error
import urllib.request

USER = sys.argv[1] if len(sys.argv) > 1 else "OSWAHH1"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


def get(url, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:400]
    except Exception as e:  # noqa
        return 0, f"{type(e).__name__}: {e}"


def walk(o, path="", out=None):
    out = [] if out is None else out
    if isinstance(o, dict):
        for k, v in o.items():
            walk(v, f"{path}.{k}", out)
        out.append((path, o))
    elif isinstance(o, list):
        for i, v in enumerate(o):
            walk(v, f"{path}[{i}]", out)
    return out


print("=== 1. syndication timeline (no login) ===")
first_id = None
for host in ("syndication.twitter.com", "syndication.x.com"):
    url = f"https://{host}/srv/timeline-profile/screen-name/{USER}?showReplies=false"
    status, body = get(url)
    print(f"[{host}] status={status} bytes={len(body)}")
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', body, re.S)
    if not m:
        print("   no __NEXT_DATA__;", body[:160].replace("\n", " "))
        continue
    try:
        data = json.loads(m.group(1))
    except Exception as e:  # noqa
        print("   bad json", e)
        continue
    tweets = [o for _, o in walk(data) if isinstance(o, dict) and ("full_text" in o or "text" in o) and "created_at" in o and "id_str" in o]
    print(f"   tweets found: {len(tweets)}")
    if tweets:
        t = tweets[0]
        first_id = first_id or t.get("id_str")
        print("   keys of first tweet:", sorted(t.keys()))
        view_keys = sorted({k for tw in tweets for k in tw if "view" in k.lower() or "impression" in k.lower()})
        print("   view-like keys:", view_keys)
        for tw in tweets[:5]:
            print("   ", tw.get("id_str"), tw.get("created_at"), {k: tw[k] for k in tw if "view" in k.lower() or k in ("favorite_count", "reply_count", "retweet_count")})
    break

print("\n=== 2. single-tweet embed endpoint ===")
if first_id:
    for token in ("a", "0"):
        status, body = get(f"https://cdn.syndication.twimg.com/tweet-result?id={first_id}&lang=en&token={token}")
        print(f"[token={token}] status={status} bytes={len(body)}")
        try:
            j = json.loads(body)
            print("   keys:", sorted(j.keys()))
            print("   view-like:", {k: j[k] for k in j if "view" in k.lower()})
            break
        except Exception:
            print("   ", body[:160].replace("\n", " "))
else:
    print("skipped: no tweet id from step 1")

print("\n=== 3. public mirrors (nitter-style) ===")
for host in ("nitter.net", "nitter.poast.org", "nitter.privacydev.net"):
    status, body = get(f"https://{host}/{USER}")
    print(f"[{host}] status={status} has_tweets={'timeline-item' in body}")

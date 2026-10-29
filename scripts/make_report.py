#!/usr/bin/env python3
"""Monthly impact report (PDF) for the Uswah site.

A month's report is published only once the month is over AND the X account has data for it
(X numbers are entered by hand, so the report waits for them). Until then the site shows the
report as "not available for download".

    python3 scripts/make_report.py --check   # update the index in data/stats.json; print pending=true|false
    python3 scripts/make_report.py           # also render the pending PDFs into reports/ (needs playwright)

Environment: REPORT_TODAY=YYYY-MM-DD (testing), REPORT_FORCE=1 (ignore the "X data present" rule, testing).
"""
import base64
import datetime as dt
import hashlib
import html
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "stats.json"
OUT = ROOT / "reports"
FONTS = ROOT / "assets" / "fonts"

PLATFORMS = [("x", "إكس (X)"), ("telegram", "تيليجرام"), ("youtube", "يوتيوب"), ("tiktok", "تيك توك")]
MONTHS = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
POEM_RE = re.compile(r"قصيد|منظوم|نظم|أنشود|نشيد")


def day(s):
    return dt.date.fromisoformat(str(s)[:10])


def month_label(d):
    return f"{MONTHS[d.month - 1]} {d.year}"


def today():
    return day(os.environ.get("REPORT_TODAY") or dt.date.today().isoformat())


# --------------------------------------------------------------------------- numbers
def compute(data, a, b):
    """Same rules as the site: account totals per period (pro-rata when only partly inside the
    range) plus posts not already covered by such a period."""
    out = {}
    for pf, _ in PLATFORMS:
        periods = [r for r in data.get("periods", []) if r["platform"] == pf]
        covered = lambda d: any(day(r["from"]) <= d <= day(r["to"]) for r in periods)
        total, estimate = 0.0, False
        for r in periods:
            f, t = day(r["from"]), day(r["to"])
            ov = (min(b, t) - max(a, f)).days + 1
            if ov <= 0:
                continue
            frac = ov / ((t - f).days + 1)
            total += r["views"] * frac
            estimate = estimate or frac < 1
        posts = [p for p in data.get("posts", []) if p["platform"] == pf and a <= day(p["date"]) <= b]
        for p in posts:
            if not covered(day(p["date"])):
                total += p["views"]
        out[pf] = {"views": round(total), "estimate": estimate, "has": bool(posts or total)}
    return out


def kind_of(p):
    c = p.get("category") or ""
    if c == "audio":
        return "poems" if POEM_RE.search(p.get("title", "")) else "books"
    return {"salawat": "salawat", "quotes": "quotes", "shamail": "shamail"}.get(c, "other")


def metrics(data, a, b):
    views = compute(data, a, b)
    posts = [p for p in data.get("posts", []) if a <= day(p["date"]) <= b and p.get("category") != "announcement"]
    counts = {k: 0 for k in ("salawat", "quotes", "shamail", "books", "poems", "other")}
    for p in posts:
        counts[kind_of(p)] += 1
    top = sorted(posts, key=lambda p: -p["views"])[:3]
    return {
        "from": a.isoformat(), "to": b.isoformat(),
        "views": views, "total": sum(v["views"] for v in views.values()),
        "counts": counts, "posts": len(posts),
        "top": [{"title": p.get("title", ""), "platform": p["platform"], "views": p["views"], "date": p["date"]} for p in top],
    }


# --------------------------------------------------------------------------- index
def has_x(data, a, b):
    if any(p["platform"] == "x" and a <= day(p["date"]) <= b for p in data.get("posts", [])):
        return True
    return any(r["platform"] == "x" and day(r["from"]) <= b and day(r["to"]) >= a for r in data.get("periods", []))


def build_index(data):
    since = day(data.get("since") or "2026-08-27")
    now = today()
    prev = {r["id"]: r for r in data.get("reports", [])}
    out, y, m = [], since.year, since.month
    while (y, m) <= (now.year, now.month):
        first = dt.date(y, m, 1)
        last = (dt.date(y + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1))
        a, b = max(first, since), min(last, now)
        rid = f"{y}-{m:02d}"
        ended = last < now
        if ended and (b - a).days + 1 < 7:  # a few leftover days of the launch month: no report
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
            continue
        x_ok = has_x(data, a, b) or os.environ.get("REPORT_FORCE") == "1"
        met = metrics(data, a, b) if ended and x_ok else None
        h = hashlib.sha1(json.dumps(met, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12] if met else ""
        old = prev.get(rid, {})
        fname = f"reports/uswah-impact-{rid}.pdf"
        built = bool(met) and old.get("hash") == h and (ROOT / fname).exists()
        reason = "" if met else ("الشهر لم ينتهِ بعد" if not ended else "بانتظار إدخال بيانات منصة X")
        out.append({
            "id": rid, "label": month_label(first), "from": a.isoformat(), "to": b.isoformat(),
            "partial": a != first, "available": built, "pending": bool(met) and not built,
            "file": fname if built else "", "hash": h, "reason": reason,
        })
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


# --------------------------------------------------------------------------- HTML
def font_css():
    faces = []
    for wt in (400, 600, 700):
        for sub, rng in (("arabic", "U+0600-06FF,U+0750-077F,U+08A0-08FF,U+FB50-FDFF,U+FE70-FEFF,U+200C-200F,U+2010-2011,U+204F,U+25CC,U+FE70-FE7F"), ("latin", "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+2000-206F,U+2074,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD")):
            b64 = base64.b64encode((FONTS / f"ibm-plex-sans-arabic-{sub}-{wt}-normal.woff2").read_bytes()).decode()
            faces.append(f"@font-face{{font-family:'Plex';font-weight:{wt};src:url(data:font/woff2;base64,{b64}) format('woff2');unicode-range:{rng}}}")
    return "\n".join(faces)


def logo_uri():
    page = (ROOT / "_src" / "uswah.html").read_text(encoding="utf-8")
    m = re.search(r'--logo:url\("(data:image/png;base64,[^"]+)"\)', page)
    return m.group(1) if m else ""


EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE00-\uFE0F\u200d]")


def clean(s):
    return re.sub(r"\s+", " ", EMOJI.sub("", s or "")).strip()


def fmt(n):
    return f"{int(n):,}"


def render_html(data, rep, met):
    a, b = day(rep["from"]), day(rep["to"])
    acc = data.get("accounts", {})
    handle = next((v.get("handle") for v in acc.values() if v.get("handle")), "OSWAHH1")
    span = f"{a.day} {MONTHS[a.month - 1]} – {b.day} {MONTHS[b.month - 1]} {b.year}" if a.month != b.month else f"{a.day}–{b.day} {MONTHS[b.month - 1]} {b.year}"
    pf_names = dict(PLATFORMS)
    mx = max([v["views"] for v in met["views"].values()] + [1])
    pf_rows = []
    for pf, name in PLATFORMS:
        v = met["views"][pf]
        if not v["has"]:
            continue
        pf_rows.append(
            f'<div class="pf"><div class="pfh"><span class="pfn">{name}</span><span class="pfv">{fmt(v["views"])}</span></div>'
            f'<div class="bar"><i style="width:{max(2, v["views"] / mx * 100):.1f}%"></i></div>'
            f'{"<small>قيمة تقديرية لجزء من الفترة</small>" if v["estimate"] else ""}</div>')
    c = met["counts"]
    tiles = [
        ("salawat", "تصاميم أهمية الصلاة على النبي صلى الله عليه وسلم"),
        ("quotes", "اقتباسات في أهمية السيرة النبوية"),
        ("shamail", "مقاطع الشمائل"),
        ("books", "الكتب الصوتية"),
        ("poems", "القصائد والمنظومات"),
    ]
    tile_html = "".join(f'<div class="tile"><b>{c[k]}</b><span>{t}</span></div>' for k, t in tiles)
    top_rows = "".join(
        f'<li><span class="tt">{html.escape(clean(t["title"]) or "منشور")}</span><span class="tm">{pf_names[t["platform"]]}</span><span class="tv">{fmt(t["views"])}</span></li>'
        for t in met["top"]) or '<li class="none">لا توجد منشورات مفردة في هذه الفترة</li>'
    other = f' <span class="oth">(+{c["other"]} منشورات أخرى)</span>' if c["other"] else ""
    return f"""<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8">
<title>تقرير الأثر الشهري — {rep["label"]} — مركز أسوة للسيرة النبوية</title>
<style>
{font_css()}
@page{{size:A4;margin:0}}
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{width:210mm;height:297mm}}
body{{font-family:'Plex','Segoe UI',Tahoma,sans-serif;color:#2b1e29;background:#fbf7f3;font-size:12.5px;line-height:1.7;
 -webkit-print-color-adjust:exact;print-color-adjust:exact}}
.page{{position:relative;width:210mm;height:297mm;padding:0 16mm;overflow:hidden}}
.top{{position:absolute;inset:0 0 auto 0;height:9mm;background:linear-gradient(90deg,#3a2236 0 70%,#c2703d 70% 100%)}}
header{{display:flex;align-items:center;gap:18px;padding-top:17mm;padding-bottom:6mm;border-bottom:1.2px solid #e4d5c8}}
header img{{height:58px}}
header .ttl{{flex:1}}
header small{{display:block;color:#c2703d;font-weight:600;letter-spacing:.02em;font-size:12px}}
header h1{{font-size:28px;line-height:1.3;color:#3a2236;font-weight:700}}
header .per{{text-align:left;color:#6b5866;font-size:12px;line-height:1.5}}
header .per b{{display:block;color:#3a2236;font-size:19px;font-weight:700}}
.hero{{margin-top:7mm;background:#3a2236;color:#fbf7f3;border-radius:16px;padding:7mm 10mm;display:flex;align-items:center;justify-content:space-between;position:relative;overflow:hidden}}
.hero:before{{content:"";position:absolute;left:-30mm;top:-30mm;width:80mm;height:80mm;border-radius:50%;border:14mm solid rgba(194,112,61,.28)}}
.hero .lb{{font-size:13px;color:#e9d6c8;position:relative}}
.hero .big{{font-size:58px;font-weight:700;line-height:1.15;color:#fff;font-variant-numeric:tabular-nums;position:relative}}
.hero .big small{{font-size:17px;font-weight:600;color:#e2a67f;margin-inline-start:8px}}
.hero .side{{text-align:center;position:relative;z-index:1;font-size:12px;color:#e9d6c8;line-height:1.6;border-inline-start:1px solid rgba(255,255,255,.22);padding-inline-start:9mm}}
.hero .side b{{color:#fff;font-size:40px;line-height:1.15;display:block;font-weight:700}}
h2{{font-size:15.5px;color:#3a2236;font-weight:700;margin:6.5mm 0 3.5mm;display:flex;align-items:center;gap:8px}}
h2:before{{content:"";width:5px;height:18px;border-radius:3px;background:#c2703d}}
.pfs{{display:grid;grid-template-columns:1fr 1fr;gap:4mm 8mm}}
.pf{{background:#fff;border:1px solid #eadfd5;border-radius:12px;padding:3.2mm 5mm}}
.pfh{{display:flex;justify-content:space-between;align-items:baseline}}
.pfn{{font-weight:600;color:#3a2236;font-size:13.5px}}
.pfv{{font-size:23px;font-weight:700;color:#c2703d;font-variant-numeric:tabular-nums}}
.bar{{height:6px;background:#f1e7de;border-radius:3px;margin-top:3mm;overflow:hidden}}
.bar i{{display:block;height:100%;background:linear-gradient(90deg,#c2703d,#d99466);border-radius:3px}}
.pf small{{color:#8c7b87;font-size:10px}}
.tiles{{display:grid;grid-template-columns:repeat(5,1fr);gap:3mm}}
.tile{{background:#fff;border:1px solid #eadfd5;border-top:3px solid #c2703d;border-radius:10px;padding:3.2mm 2mm;text-align:center}}
.tile b{{display:block;font-size:30px;line-height:1.1;color:#3a2236;font-weight:700;font-variant-numeric:tabular-nums}}
.tile span{{display:block;margin-top:2mm;font-size:10.8px;color:#6b5866;line-height:1.45;font-weight:500}}
.sum{{margin-top:3.5mm;color:#6b5866;font-size:12px}}
.sum b{{color:#3a2236}}
.oth{{color:#8c7b87}}
ol{{list-style:none;background:#fff;border:1px solid #eadfd5;border-radius:12px;overflow:hidden}}
ol li{{display:grid;grid-template-columns:1fr auto auto;gap:5mm;align-items:center;padding:2.3mm 5mm;border-bottom:1px solid #f0e6dd}}
ol li:last-child{{border:0}}
.tt{{font-weight:600;color:#3a2236;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:98mm}}
.tm{{color:#8c7b87;font-size:11px}}
.tv{{font-weight:700;color:#c2703d;min-width:22mm;text-align:left;font-variant-numeric:tabular-nums}}
.none{{display:block;color:#8c7b87}}
footer{{position:absolute;inset:auto 16mm 8mm 16mm;border-top:1.2px solid #e4d5c8;padding-top:4mm;display:flex;justify-content:space-between;gap:10mm;color:#8c7b87;font-size:10.3px;line-height:1.6}}
footer b{{color:#3a2236}}
</style></head><body><div class="page"><div class="top"></div>
<header><img src="{logo_uri()}" alt="شعار مركز أسوة">
 <div class="ttl"><small>تقرير الأثر الشهري</small><h1>مركز أسوة للسيرة النبوية</h1></div>
 <div class="per"><b>{rep["label"]}</b>{span}</div></header>
<section class="hero"><div><div class="lb">إجمالي المشاهدات على جميع المنصات</div><div class="big">{fmt(met["total"])}<small>مشاهدة</small></div></div>
 <div class="side"><b>{met["posts"]}</b>منشورًا خلال الفترة<br>{other}</div></section>
<h2>المشاهدات حسب المنصة</h2><div class="pfs">{"".join(pf_rows)}</div>
<h2>المحتوى المنشور</h2><div class="tiles">{tile_html}</div>
<p class="sum">إجمالي المنشورات: <b>{met["posts"]}</b>، تشمل ما نُشر على تيليجرام ويوتيوب وإكس.</p>
<h2>أعلى المنشورات مشاهدة</h2><ol>{top_rows}</ol>
<footer><div><b>uswah.sa</b> · @{handle}<br>مركز أسوة للسيرة النبوية — نتعلم.. لنتأسى</div>
<div style="text-align:left">المشاهدات المعروضة هي مشاهدات المحتوى كما تُظهرها المنصات.<br>صدر في {today().day} {MONTHS[today().month - 1]} {today().year}</div></footer>
</div></body></html>"""


def render_pdf(jobs):
    from playwright.sync_api import sync_playwright
    OUT.mkdir(exist_ok=True)
    exe = os.environ.get("CHROMIUM_PATH") or None
    with sync_playwright() as p:
        br = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        for html_text, path in jobs:
            page = br.new_page()
            page.set_content(html_text, wait_until="load")
            page.evaluate("document.fonts.ready")
            page.pdf(path=str(path), format="A4", print_background=True, prefer_css_page_size=True)
            page.close()
        br.close()


def main():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    index = build_index(data)
    data["reports"] = index
    pending = [r for r in index if r["pending"]]
    print(f"reports: {len(index)} months, {sum(r['available'] for r in index)} ready, {len(pending)} pending")
    if "--check" in sys.argv:
        out = os.environ.get("GITHUB_OUTPUT")
        if out:
            with open(out, "a") as f:
                f.write(f"pending={'true' if pending else 'false'}\n")
    else:
        jobs = []
        for r in pending:
            met = metrics(data, day(r["from"]), day(r["to"]))
            jobs.append((render_html(data, r, met), ROOT / r["file"] if r["file"] else ROOT / f"reports/uswah-impact-{r['id']}.pdf"))
        if jobs:
            render_pdf(jobs)
        for r in pending:
            r["file"] = f"reports/uswah-impact-{r['id']}.pdf"
            r["available"], r["pending"] = True, False
            print("  ✓", r["file"])
    DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    sys.path.insert(0, str(Path(__file__).parent))
    import fetch_stats
    fetch_stats.embed_in_page(data)


if __name__ == "__main__":
    main()

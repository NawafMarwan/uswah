#!/usr/bin/env python3
"""يبني academy/index.html (نموذج واجهة أكاديمية السيرة النبوية) من القالب والبيانات.

  python3 scripts/build_academy.py

المدخلات: scripts/academy_template.html و data/academy.json (الدروس والأسئلة).
المخرج:  academy/index.html (الرابط uswah.sa/academy/)، صفحة مستقلة بلا بوابة دخول (تجريبية)،
         وuswah-academy.html صفحة تحويل إلى الرابط الجديد.
يحتاج مكتبة segno لتوليد رمز QR:  pip install segno
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SIRA_MAP_URL = "https://uswah.sa/sira-map"
REDIRECT = """<!DOCTYPE html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex"><title>أكاديمية السيرة النبوية — مركز أسوة</title>
<meta http-equiv="refresh" content="0; url=academy/"><link rel="canonical" href="https://uswah.sa/academy/">
<script>location.replace('academy/' + location.search + location.hash)</script></head>
<body style="font-family:system-ui,sans-serif;text-align:center;padding:40px"><p>انتقل الرابط إلى <a href="academy/">uswah.sa/academy</a>.</p></body></html>
"""


def qr_svg() -> str:
    import segno
    code = segno.make(SIRA_MAP_URL, error="m")
    svg = code.svg_inline(scale=1, border=1, dark="#2e1c2b", light="#ffffff", omitsize=True)
    assert "`" not in svg and "${" not in svg
    return svg


# النموذج لا يعرض مصادر النصوص والمقاطع (بطلب المركز): تبقى في data/academy.json للتوثيق الداخلي وتُحذف من الصفحة.
SRC_PATTERNS = [
    (r"\s*\((?:[^()]*\d+\s*/\s*\d+[^()]*|[^()]*(?:ص|صفحة)\s*\d+[^()]*)\)", ""),   # (سيرة ابن هشام 1/163) ونحوها
    (r"^(?:قال|وقال|روى|وروى|ذكر)\s+(?:ابن هشام|ابن إسحاق|ابن سعد|ابن كثير|المباركفوري)\s*:\s*", ""),
    (r"\s*فيما بلغ ابن إسحاق", ""),
    (r"^قال:\s*", ""),
    (r"^ذكر ابن هشام أن ", ""),
    (r"^نص ابن إسحاق على أنه ", "النبي "),
    (r"^نقل ابن كثير عن ابن هشام:\s*", ""),
    (r"^ذكر المباركفوري رواية مسلم عن أنس:\s*", "في حديث أنس: "),
    (r"في رواية مسلم عن أنس", "في حديث أنس"),
    (r"في رواية خالد بن معدان عند ابن إسحاق", "في رواية خالد بن معدان"),
    (r"كما في حديث(ها)? (عائشة )?عند ابن إسحاق", r"كما في حديث\1 \2"),
    (r"عند ابن إسحاق في سيرة ابن هشام،\s*", ""),
    (r"،?\s*(?:كما ورد في متن|كما في|في) سيرة ابن هشام", ""),
    (r"،?\s*(?:عند|كما ذكر|في رواية) (?:ابن إسحاق|ابن هشام)", ""),
    (r"،?\s*بحسب «?الرحيق المختوم»?،?", ""),
]


def nosrc(t):
    if not isinstance(t, str):
        return t
    for a, b in SRC_PATTERNS:
        t = re.sub(a, b, t)
    t = re.sub(r"\s+([،.؟])", r"\1", t)
    t = re.sub(r"\s{2,}", " ", t).strip()
    return t[:1].upper() + t[1:] if t else t


def main():
    data = json.loads((ROOT / "data" / "academy.json").read_text(encoding="utf-8"))
    for l in data["lessons"]:
        assert len(l["questions"]) >= 20, (l["id"], len(l["questions"]))
        for q in l["questions"]:
            assert len(q) == 6 and len(set(q[1:5])) == 4, q
    # ---- خطوات الخريطة داخل كل درس: إحداثيات الأماكن من سجل الخريطة التفاعلية ----
    reg, aliases = {}, {}
    for f in sorted((ROOT / "data" / "sira").glob("places*.json")):
        pd = json.loads(f.read_text(encoding="utf-8"))
        aliases.update(pd.get("aliases", {}))
        for k, v in pd.get("places", pd).items():
            if isinstance(v, dict) and v.get("ll"):
                reg[k] = v
    extra = data.get("places_extra", {})

    def place(pid):
        pid = aliases.get(pid, pid)
        if pid in extra:
            return extra[pid]["ll"], extra[pid]["ar"]
        v = reg[pid]
        return v["ll"], v["ar"].split(" (")[0]

    seed_html = (ROOT / "_src" / "sira-map.html").read_text(encoding="utf-8")
    sm = re.search(r'<script id="seed" type="application/json">(.*?)</script>', seed_html, re.S)
    events = {e["id"]: e for e in json.loads(sm.group(1).replace("<\\/", "</"))["events"]}
    for l in data["lessons"]:
        steps = l.get("steps") or []
        if l.get("from_events"):
            steps = []
            for eid in l["from_events"]:
                e = events[eid]
                s0 = (e.get("sources") or [{}])[0]
                ref = (s0.get("book", "") + " " + (f"{s0['volume']}/{s0['page']}" if s0.get("volume") is not None else f"ص{s0.get('page')}")).strip()
                steps.append({"t": e["title"], "pl": e["places"][0], "x": e["summary"], "s": ref})
        out = []
        for st in steps:
            ll, name = place(st["pl"])
            out.append({"t": st["t"], "x": st["x"], "s": st.get("s", ""), "ll": ll, "pn": name, "k": st["pl"]})
        l["steps"] = out
        l.pop("from_events", None)

    for l in data["lessons"]:
        l["questions"] = [[nosrc(x) for x in q] for q in l["questions"]]
        for st in l["steps"]:
            st["x"] = nosrc(st["x"]); st.pop("s", None)
        if l.get("hook"):
            l["hook"]["reveal"] = nosrc(l["hook"]["reveal"]); l["hook"].pop("src", None)
        if l.get("reading"):
            r = l["reading"]
            r["questions"] = [[nosrc(x) for x in q] for q in r["questions"]]
            r["body"] = [re.sub(r"\s*«[٠-٩0-9]+»\s*", " ", t).replace(" .", ".").strip() for t in r["body"]]
            for k in ("book", "author", "page", "src", "foot"):
                r.pop(k, None)
        l.pop("desc", None); l.pop("videoUrl", None)
    leak = re.findall(r"ابن هشام|ابن إسحاق|الرحيق|الطبقات|العازمي|المباركفوري|\d+/\d+", json.dumps(data["lessons"], ensure_ascii=False))
    assert not leak, ("ما زالت في الصفحة إشارات إلى مصادر", sorted(set(leak)))

    pend = [l['id'] for l in data['lessons'] if l.get('pending')]
    if pend:
        print('تنبيه: دروس أسئلتها مؤقتة بعد:', pend)
    seed = json.dumps({"lessons": data["lessons"]}, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    page = (ROOT / "_src" / "uswah.html").read_text(encoding="utf-8")
    logo = re.search(r'--logo:url\("(data:image/png;base64,[^"]+)"\)', page).group(1)
    tpl = (ROOT / "scripts" / "academy_template.html").read_text(encoding="utf-8")
    css = (ROOT / "scripts/vendor/leaflet.css").read_text(encoding="utf-8")
    js = (ROOT / "scripts/vendor/leaflet.js").read_text(encoding="utf-8").replace("</script", "<\\/script")
    html = (tpl.replace("__LEAFLET_CSS__", css).replace("__LEAFLET_JS__", js)
               .replace("__LOGO__", logo).replace("__QR__", qr_svg()).replace("__DATA__", seed)
               .replace("__GEO__", (ROOT / "data/geo/arabia.json").read_text(encoding="utf-8")))
    out = ROOT / "academy" / "index.html"          # الرابط: uswah.sa/academy/
    out.parent.mkdir(exist_ok=True)
    out.write_text(html, encoding="utf-8")
    # الرابط القديم يحوّل إلى المجلد الجديد حتى لا ينكسر ما أُرسل من روابط
    (ROOT / "uswah-academy.html").write_text(REDIRECT, encoding="utf-8")
    print(f"academy/index.html: {len(html):,} bytes، دروس: {len(data['lessons'])}، "
          f"أسئلة: {sum(len(l['questions']) for l in data['lessons'])}")


if __name__ == "__main__":
    main()

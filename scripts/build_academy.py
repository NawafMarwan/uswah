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
SIRA_MAP_URL = "https://uswah.sa/sira-map.html"
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


def main():
    data = json.loads((ROOT / "data" / "academy.json").read_text(encoding="utf-8"))
    for l in data["lessons"]:
        assert len(l["questions"]) >= 20, (l["id"], len(l["questions"]))
        for q in l["questions"]:
            assert len(q) == 6 and len(set(q[1:5])) == 4, q
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
               .replace("__LOGO__", logo).replace("__QR__", qr_svg()).replace("__DATA__", seed))
    out = ROOT / "academy" / "index.html"          # الرابط: uswah.sa/academy/
    out.parent.mkdir(exist_ok=True)
    out.write_text(html, encoding="utf-8")
    # الرابط القديم يحوّل إلى المجلد الجديد حتى لا ينكسر ما أُرسل من روابط
    (ROOT / "uswah-academy.html").write_text(REDIRECT, encoding="utf-8")
    print(f"academy/index.html: {len(html):,} bytes، دروس: {len(data['lessons'])}، "
          f"أسئلة: {sum(len(l['questions']) for l in data['lessons'])}")


if __name__ == "__main__":
    main()

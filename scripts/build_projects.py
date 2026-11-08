#!/usr/bin/env python3
"""يولّد قسم «المشاريع النوعية» في _src/uswah.html من data/projects.json.

القسم محصور بين العلامتين <!--PROJECTS:START--> و<!--PROJECTS:END-->؛ يُستبدل ما بينهما
في كل تشغيل، فلا تعدّل ذلك الجزء يدويًا. عدّل data/projects.json ثم شغّل هذا السكربت.
"""
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "_src" / "uswah.html"
DATA = ROOT / "data" / "projects.json"
START, END = "<!--PROJECTS:START-->", "<!--PROJECTS:END-->"

e = lambda s: html.escape(str(s), quote=True)

HEART = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 20.5s-7.5-4.6-7.5-10.2A4.3 4.3 0 0 1 12 7.6a4.3 4.3 0 0 1 7.5 2.7c0 5.6-7.5 10.2-7.5 10.2z"/></svg>'


def ar_count(n, one, two, few, many):
    if n == 1:
        return one
    if n == 2:
        return two
    return f"{n} {few if 3 <= n <= 10 else many}"


def card(i, p):
    sup = p.get("supported")
    badge = (f'<span class="sup-badge" title="مشروع مدعوم" aria-label="مشروع مدعوم">{HEART}<small>مدعوم</small></span>'
             if sup else "")
    objs, phases, spins = p.get("objectives", []), p.get("phases", []), p.get("spinoffs", [])
    meta = [ar_count(len(objs), "هدف تفصيلي واحد", "هدفان تفصيليان", "أهداف تفصيلية", "هدفًا تفصيليًا")]
    if phases:
        meta.append(ar_count(len(phases), "مرحلة واحدة", "مرحلتان", "مراحل", "مرحلة"))
    if spins:
        meta.append(ar_count(len(spins), "مشروع منبثق", "مشروعان منبثقان", "مشاريع منبثقة", "مشروعًا منبثقًا"))
    out = [f'<article class="proj{" sup" if sup else ""}" id="proj-{e(p["id"])}">']
    out.append(f'<header class="ph"><span class="pn num">{i}</span><h2>{e(p["title"])}</h2>{badge}</header>')
    out.append(f'<p class="pgoal"><b>الهدف العام</b>{e(p["goal"])}</p>')
    out.append('<div class="pmeta">' + "".join(f"<span>{e(m)}</span>" for m in meta) + "</div>")
    body = [f'<section class="pb"><h3>التعريف بالمشروع</h3><p>{e(p["definition"])}</p></section>']
    body.append('<section class="pb"><h3>الأهداف التفصيلية</h3><ol class="pobj">'
                + "".join(f"<li>{e(o)}</li>" for o in objs) + "</ol></section>")
    if phases:
        body.append('<section class="pb"><h3>المراحل</h3><ol class="pphases">' + "".join(
            f'<li><b>{e(ph["title"])}</b><ul>' + "".join(f"<li>{e(x)}</li>" for x in ph["items"]) + "</ul></li>"
            for ph in phases) + "</ol></section>")
    if spins:
        body.append('<section class="pb"><h3>المشاريع المنبثقة</h3><div class="pspin">'
                    + "".join(f"<span>{e(s)}</span>" for s in spins) + "</div></section>")
    tech, admin = p.get("tech_needs", []), p.get("admin_needs", [])
    if tech or admin:
        def needs(title, items, cls):
            return (f'<section class="pb pneeds {cls}"><h3>{title}</h3><ul class="pneed">'
                    + "".join(f"<li>{e(x)}</li>" for x in items) + "</ul></section>")
        body.append('<div class="pneeds-wrap">'
                    + (needs("الاحتياجات الفنية", tech, "tech") if tech else "")
                    + (needs("الاحتياجات الإدارية", admin, "admin") if admin else "") + "</div>")
    out.append('<details class="pd"><summary><span>تفاصيل المشروع</span><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg></summary><div class="pbody">'
               + "".join(body) + "</div></details>")
    out.append("</article>")
    return "".join(out)


def build():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    cards = "\n".join(card(i + 1, p) for i, p in enumerate(data["projects"]))
    sup_n = sum(1 for p in data["projects"] if p.get("supported"))
    main = f'''{START}
<main id="projects" data-page="projects" hidden>
  <div class="wrap">
    <div class="dash-head">
      <div>
        <h1>المشاريع النوعية</h1>
        <p>مبادرات نوعية يسعى المركز إلى تنفيذها في الفترة المقبلة بإذن الله</p>
      </div>
      <span class="sup-badge legend" title="مشروع مدعوم">{HEART}<small>مشروع مدعوم · {sup_n} من {len(data["projects"])}</small></span>
    </div>
    <div class="proj-grid">
{cards}
    </div>
  </div>
</main>
{END}'''
    page = PAGE.read_text(encoding="utf-8")
    if START in page:
        page = re.sub(re.escape(START) + r".*?" + re.escape(END), lambda m: main, page, flags=re.S)
    else:
        anchor = '<main id="plan" data-page="plan" hidden>'
        assert anchor in page
        page = page.replace(anchor, main + "\n\n" + anchor, 1)
    PAGE.write_text(page, encoding="utf-8")
    print(f"projects: {len(data['projects'])} ({sup_n} مدعومان)")


if __name__ == "__main__":
    build()

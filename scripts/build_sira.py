#!/usr/bin/env python3
"""Builds _src/sira-map.html (the interactive Sira map) from the verified research files.

  data/sira/manifest.json   which research files are published, and the coverage sentence
  data/sira/*.json          events documented from "المكتبة الشاملة" (one file per phase)
  data/sira/places.json     place registry (coordinates, quality) and region labels

Run after changing any of them, then scripts/protect.py (the Action does that) to encrypt the page.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data" / "sira"
OUT = ROOT / "_src" / "sira-map.html"


def main():
    man = json.loads((D / "manifest.json").read_text(encoding="utf-8"))
    reg = json.loads((D / "places.json").read_text(encoding="utf-8"))
    places, events = reg["places"], []
    for name in man["published"]:
        events += json.loads((D / name).read_text(encoding="utf-8"))["events"]
    errors = []
    for e in events:
        if len(e.get("sources", [])) < 2:
            errors.append(f"{e['id']}: fewer than 2 sources")
        for p in list(e.get("places", [])) + list(e.get("route", [])):
            if p not in places:
                errors.append(f"{e['id']}: unknown place '{p}'")
        for s in e.get("sources", []):
            if not s.get("quote") or not s.get("page"):
                errors.append(f"{e['id']}: source without quote/page")
    if errors:
        sys.exit("\n".join(errors))
    used = {p for e in events for p in list(e.get("places", [])) + list(e.get("route", []))}
    data = {
        "events": events,
        "places": {k: v for k, v in places.items() if k in used},
        "regions": reg.get("regions", []),
        "meta": {"coverage": man.get("coverage", ""), "count": len(events)},
    }
    tpl = (ROOT / "scripts" / "sira_template.html").read_text(encoding="utf-8")
    page = (ROOT / "_src" / "uswah.html").read_text(encoding="utf-8")
    logo = re.search(r'--logo:url\("(data:image/png;base64,[^"]+)"\)', page).group(1)
    seed = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = (tpl.replace("__LEAFLET_CSS__", (ROOT / "scripts/vendor/leaflet.css").read_text(encoding="utf-8"))
               .replace("__LEAFLET_JS__", (ROOT / "scripts/vendor/leaflet.js").read_text(encoding="utf-8").replace("</script", "<\\/script"))
               .replace("__LOGO__", logo).replace("__SEED__", seed))
    OUT.write_text(html, encoding="utf-8")
    print(f"✓ {OUT.relative_to(ROOT)}: {len(events)} events, {len(data['places'])} places, {len(html):,} bytes")


if __name__ == "__main__":
    main()

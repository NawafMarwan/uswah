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


def load_places(man):
    places, regions, aliases = {}, [], {}
    for name in man.get("places_files", ["places.json"]):
        reg = json.loads((D / name).read_text(encoding="utf-8"))
        for k, v in reg["places"].items():
            places.setdefault(k, v)
        regions = regions or reg.get("regions", [])
        aliases.update(reg.get("aliases", {}))
    return places, regions, aliases


def main():
    man = json.loads((D / "manifest.json").read_text(encoding="utf-8"))
    places, regions, aliases = load_places(man)
    events = []
    for name in man["published"]:
        events += json.loads((D / name).read_text(encoding="utf-8"))["events"]

    # Chronological placement across research files: events are moved (text untouched) after a given event.
    for rule in man.get("moves", []):
        ids = rule["ids"]
        moved = [e for e in events if e["id"] in ids]
        events = [e for e in events if e["id"] not in ids]
        pos = next((i for i, e in enumerate(events) if e["id"] == rule["after"]), None)
        if pos is None:
            sys.exit(f"move: unknown anchor {rule['after']}")
        events[pos + 1:pos + 1] = sorted(moved, key=lambda e: ids.index(e["id"]))

    # Which places are drawn: only those with a point; several "area" places that share one centre
    # (stacked guesses) are not drawn at all. Their names stay in the event text.
    centre = {}
    for k, v in places.items():
        if v.get("ll"):
            centre.setdefault(tuple(v["ll"]), []).append(k)
    def drawable(k):
        v = places.get(k)
        if not v or not v.get("ll") or v.get("q") == "none":
            return False
        if v.get("q") == "area" and len(centre[tuple(v["ll"])]) >= 3:
            return False
        return True

    errors, unmapped = [], 0
    for e in events:
        if len(e.get("sources", [])) < 2:
            errors.append(f"{e['id']}: fewer than 2 sources")
        for s in e.get("sources", []):
            if not s.get("quote") or not s.get("page"):
                errors.append(f"{e['id']}: source without quote/page")
        names = e.get("place_names_ar") or {}
        ids = [aliases.get(p, p) for p in e.get("places", [])]
        rt = [aliases.get(p, p) for p in e.get("route", [])]
        for p in ids + rt:
            if p not in places:
                errors.append(f"{e['id']}: unknown place '{p}'")
        shown = [p for p in dict.fromkeys(ids) if drawable(p)]
        e["hidden_places"] = [places[p]["ar"] if p in places else p for p in dict.fromkeys(ids) if p in places and not drawable(p)]
        unmapped += len(e["hidden_places"])
        e["places"] = shown
        e["route"] = [p for p in rt if drawable(p)]
        e.pop("place_names_ar", None)
        e.pop("internal_notes", None)
    if errors:
        sys.exit("\n".join(errors))
    used = {p for e in events for p in list(e["places"]) + list(e["route"])}
    keep = ("ar", "kind", "ll", "q", "r", "minz", "modern", "bilady", "bilady_quote")
    data = {
        "events": events,
        "places": {k: {f: v[f] for f in keep if f in v} for k, v in places.items() if k in used},
        "regions": regions,
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
    print(f"✓ {OUT.relative_to(ROOT)}: {len(events)} events, {len(data['places'])} places drawn, {unmapped} place mentions kept as text only, {len(html):,} bytes")


if __name__ == "__main__":
    main()

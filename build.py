#!/usr/bin/env python3
"""Inline the newest reading and the player portraits into dashboard.html.

Both go inline on purpose. The reading, so the page is never blank on open;
the portraits, because the artifact runtime does not serve published files at
their own paths and its CSP drops inline onerror handlers, so a src-and-fallback
approach silently renders nothing.
"""
import argparse
import base64
import json
import os

parser = argparse.ArgumentParser()
parser.add_argument("--data-url", default="", help="poll this JSON for live readings")
parser.add_argument("--out", default="dashboard.html")
parser.add_argument("--standalone", action="store_true",
                    help="wrap in a full document; the artifact runtime supplies its own")
args = parser.parse_args()

here = os.path.dirname(os.path.abspath(__file__))

tpl = open(os.path.join(here, "dashboard.template.html")).read()
state = json.load(open(os.path.join(here, "state.json")))

photos = {}
photo_dir = os.path.join(here, "photos")
if os.path.isdir(photo_dir):
    for name in sorted(os.listdir(photo_dir)):
        if not name.endswith(".png"):
            continue
        with open(os.path.join(photo_dir, name), "rb") as fh:
            photos[name] = "data:image/png;base64," + base64.b64encode(fh.read()).decode()

out = tpl.replace("/*__SNAPSHOT__*/ null", json.dumps(state, separators=(",", ":")))
badges = {k: v for k, v in photos.items() if "-club-" in k}
faces = {k: v for k, v in photos.items() if "-club-" not in k}
out = out.replace("/*__PHOTOS__*/ {}", json.dumps(faces, separators=(",", ":")))
out = out.replace("/*__BADGES__*/ {}", json.dumps(badges, separators=(",", ":")))
out = out.replace('/*__DATA_URL__*/ ""', json.dumps(args.data_url))

if args.standalone:
    # The artifact runtime wraps the fragment in a document with a charset and a
    # viewport meta. Nothing does that on GitHub Pages, and without the viewport
    # mobile Safari lays the page out at 980px and shrinks it to fit, so none of
    # the responsive breakpoints ever fire.
    head, marker, body = out.partition('<div class="wrap">')
    out = (
        '<!doctype html>\n<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<meta name="color-scheme" content="light dark">\n'
        '<meta name="description" content="Live gameweek points for four fantasy teams.">\n'
        '<link rel="icon" type="image/png" sizes="32x32" href="favicon-32.png">\n'
        '<link rel="icon" type="image/png" sizes="180x180" href="favicon-180.png">\n'
        '<link rel="apple-touch-icon" href="apple-touch-icon.png">\n'
        '<link rel="manifest" href="manifest.webmanifest">\n'
        '<meta name="apple-mobile-web-app-title" content="Matchday">\n'
        '<meta name="apple-mobile-web-app-capable" content="yes">\n'
        '<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">\n'
        '<meta name="theme-color" content="#111621">\n'
        '<style>img{max-width:100%}[hidden]{display:none!important}</style>\n'
        + head
        + '</head>\n<body>\n'
        + marker + body
        + '\n</body>\n</html>\n'
    )

dest = args.out if os.path.isabs(args.out) else os.path.join(here, args.out)
os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
open(dest, "w").write(out)
print(f"{args.out} {len(out) / 1024:.0f} KB · {len(faces)} portraits, {len(badges)} badges inlined"
      + (f" · polling {args.data_url}" if args.data_url else ""))

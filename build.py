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
out = out.replace("/*__PHOTOS__*/ {}", json.dumps(photos, separators=(",", ":")))
out = out.replace('/*__DATA_URL__*/ ""', json.dumps(args.data_url))

dest = args.out if os.path.isabs(args.out) else os.path.join(here, args.out)
os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
open(dest, "w").write(out)
print(f"{args.out} {len(out) / 1024:.0f} KB · {len(photos)} portraits inlined"
      + (f" · polling {args.data_url}" if args.data_url else ""))

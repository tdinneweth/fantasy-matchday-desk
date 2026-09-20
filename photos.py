#!/usr/bin/env python3
"""Fetch the official portraits for every player currently in the four squads.

Both games serve their own player images, so nothing third-party is involved:
  FPL          resources.premierleague.com  (p<code>.png)
  Pro League   fanarena S3                  (portraitUrl on the player record)

Images are downsized with sips so the whole set ships with the artifact cheaply.
Players without a portrait (Pro League serves a club dummy for some) are skipped
and the page falls back to initials.
"""

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "photos")
STATE = os.path.join(HERE, "state.json")
FPL_PHOTO = "https://resources.premierleague.com/premierleague/photos/players/110x140/p{}.png"
FPL_BADGE = "https://resources.premierleague.com/premierleague/badges/70/t{}.png"
PRO_BADGE = "https://fanarena.s3.eu-west-1.amazonaws.com/badges/club_{}.png"
UCL_BADGE = "https://img.uefa.com/imgml/TP/teams/logos/70x70/{}.png"
# some players only exist under the newer path, without the "p" prefix
FPL_PHOTO_ALT = "https://resources.premierleague.com/premierleague25/photos/players/110x140/{}.png"
WIDTH = 96


def squads():
    state = json.load(open(STATE))
    teams = ((state.get("fpl") or {}).get("teams") or []) \
        + ((state.get("pro") or {}).get("teams") or []) \
        + ((state.get("ucl") or {}).get("teams") or [])
    wanted = {}
    for t in teams:
        for p in t.get("squad", []):
            name = p.get("photo")
            if not name:
                continue
            if name.startswith("fpl-"):
                code = name[4:-4]
                wanted[name] = [FPL_PHOTO.format(code), FPL_PHOTO_ALT.format(code)]
            elif p.get("photoSource"):
                wanted[name] = [p["photoSource"]]

    # club badges, named by the fixtures that reference them
    fixtures = ((state.get("fpl") or {}).get("matches") or []) + \
               ((state.get("pro") or {}).get("matches") or []) + \
               ((state.get("ucl") or {}).get("matches") or [])
    for m in fixtures:
        for key in ("homeBadge", "awayBadge"):
            name = m.get(key)
            if not name or name in wanted:
                continue
            ident = name.rsplit("-", 1)[-1].rsplit(".", 1)[0]
            source = (FPL_BADGE if name.startswith("fpl-")
                      else UCL_BADGE if name.startswith("ucl-")
                      else PRO_BADGE)
            wanted[name] = [source.format(ident)]
    return wanted


def main():
    os.makedirs(OUT, exist_ok=True)
    wanted = squads()
    keep, fetched, failed = set(), 0, []

    for name, urls in sorted(wanted.items()):
        keep.add(name)
        path = os.path.join(OUT, name)
        if os.path.exists(path) and os.path.getsize(path) > 0:
            continue
        got = False
        for url in urls:
            subprocess.run(["curl", "-sS", "-m", "30", "-o", path, url], capture_output=True, text=True)
            if os.path.exists(path) and os.path.getsize(path) >= 512:
                got = True
                break
            if os.path.exists(path):
                os.remove(path)
        if not got:
            failed.append(name)
            continue
        # badges are shown small and sit beside every fixture
        subprocess.run(["sips", "-Z", "56" if "-club-" in name else str(WIDTH), path],
                       capture_output=True)
        fetched += 1

    # drop portraits for players who have left the squads
    for stale in set(os.listdir(OUT)) - keep:
        os.remove(os.path.join(OUT, stale))

    total = sum(os.path.getsize(os.path.join(OUT, f)) for f in os.listdir(OUT))
    print(f"{len(keep)} wanted · {fetched} downloaded · {len(failed)} failed · "
          f"{total / 1024:.0f} KB total")
    if failed:
        print("no portrait for: " + ", ".join(failed), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Push newly spotted ticker events to an ntfy topic.

Reads new-events.json, which refresh.py writes each pass, and announces only what
moves a score: goals, assists and red cards. Bonus points are deliberately left
out — they recalculate repeatedly while a match is on and would be the noisiest
thing here by a distance.

The topic name is the only secret; it arrives in NTFY_TOPIC and never lands in
the repo. Nothing is sent when it is unset, so local runs stay quiet.
"""

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NEW_EVENTS = os.path.join(HERE, "new-events.json")
SITE = "https://tdinneweth.github.io/fantasy-matchday-desk/"

WORTH_A_BUZZ = {"goal", "assist", "red"}
TAGS = {"goal": "soccer", "assist": "handshake", "red": "red_circle"}


def post(topic, event):
    points = event.get("points")
    title = "%s — %s%s" % (
        event["player"],
        event["label"],
        "" if points is None else " %+d" % points,
    )

    who = []
    for team in event.get("teams") or []:
        label = team["team"]
        if team.get("multiplier", 1) > 1:
            label += " ×%d" % team["multiplier"]
        if team.get("bench"):
            label += " (bench)"
        who.append(label)

    line = [", ".join(who)] if who else []
    if event.get("club"):
        line.append(event["club"] + (" " + event["opponent"] if event.get("opponent") else ""))
    if event.get("score"):
        line.append(event["score"])
    if event.get("minute") is not None:
        line.append("%s'" % event["minute"])

    body = {
        "topic": topic,
        "title": title,
        "message": " · ".join(line),
        "tags": [TAGS.get(event["kind"], "soccer")],
        "click": SITE,
    }

    out = subprocess.run(
        ["curl", "-sS", "-m", "20", "-X", "POST", "https://ntfy.sh",
         "-H", "Content-Type: application/json",
         "-d", json.dumps(body, ensure_ascii=False)],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        print("ntfy failed: %s" % out.stderr.strip(), file=sys.stderr)
        return False
    return True


def main():
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not topic:
        print("no NTFY_TOPIC set — nothing sent")
        return 0
    if not os.path.exists(NEW_EVENTS):
        print("no new-events.json — nothing sent")
        return 0

    with open(NEW_EVENTS) as fh:
        payload = json.load(fh)

    if payload.get("coldStart"):
        print("cold start — staying quiet")
        return 0

    worth = [e for e in payload.get("events", []) if e.get("kind") in WORTH_A_BUZZ]
    sent = sum(1 for e in worth if post(topic, e))
    print("%d new event%s, %d notified" % (len(payload.get("events", [])),
                                           "" if len(payload.get("events", [])) == 1 else "s",
                                           sent))
    return 0


if __name__ == "__main__":
    sys.exit(main())

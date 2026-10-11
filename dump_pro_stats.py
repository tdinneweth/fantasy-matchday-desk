#!/usr/bin/env python3
"""One-off: learn what each Pro League stat is worth, from confirmed weeks."""
import json
from collections import defaultdict
import refresh as r

headers = {"Authorization": f"Bearer {r.pro_token()}"}
PAIRS = {}
pts_fields = ["goals", "ownGoal", "penaltyGoals", "penaltySave", "penaltyMiss", "strokeGoals",
              "awards", "playedUpTo60Min", "playedMoreThan60Min", "threeOrFourGoalsAgainst",
              "fiveOrMoreGoalsAgainst", "inStarting", "assists", "yellow", "green", "red",
              "cleanSheet", "conceeded", "halfTime", "teamResultPoints", "MotM", "skillBonus",
              "bigChanceCreated", "headClearance", "ballRecovery", "duels", "interception",
              "dispossessed", "shotOffTarget", "errorLeadToGoal", "saves", "matchStatPoints",
              "matchStatTeamPoints"]
seen = defaultdict(lambda: defaultdict(int))
totals_ok = totals_bad = 0
bad = []
for week in (5, 6, 7):
    rows = r.get(f"{r.PRO}/players-stats?{r.PRO_Q}&weekId={week}&pageNumber=1&pageRecords=800",
                 headers=headers).get("data") or []
    for row in rows:
        pos = row.get("positionId")
        for f in pts_fields:
            stat = row.get("stat" + f[0].upper() + f[1:])
            if f == "duels":
                stat = (row.get("statDuelWon"), row.get("statDuelLost"))
            if f == "skillBonus":
                stat = row.get("statSkillBonus")
            seen[f][(pos, json.dumps(stat), row.get(f))] += 1
        s = sum(row.get(f) or 0 for f in pts_fields if f not in ("matchStatPoints", "matchStatTeamPoints"))
        if s == row.get("total"):
            totals_ok += 1
        else:
            totals_bad += 1
            if len(bad) < 5:
                bad.append({k: v for k, v in row.items() if not k.startswith("stat") and k != "generalInfo"})
for f in pts_fields:
    items = sorted(seen[f].items(), key=lambda kv: (kv[0][0] or 0, kv[0][1]))
    print("FIELD", f, " | ".join("pos%s stat=%s pts=%s x%d" % (k[0], k[1], k[2], n) for k, n in items[:40]))
print("TOTALS ok", totals_ok, "bad", totals_bad)
for b in bad:
    print("BAD", json.dumps(b))

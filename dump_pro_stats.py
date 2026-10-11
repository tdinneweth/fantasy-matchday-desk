#!/usr/bin/env python3
"""One-off: check pro_drivers against confirmed totals, and show live records."""
import json
from collections import Counter
import refresh as r

headers = {"Authorization": f"Bearer {r.pro_token()}"}
POS = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
ok, bad = Counter(), []
for week in (5, 6, 7):
    rows = r.get(f"{r.PRO}/players-stats?{r.PRO_Q}&weekId={week}&pageNumber=1&pageRecords=800",
                 headers=headers).get("data") or []
    for row in rows:
        n = lambda k: row.get(k) or 0
        detail = {
            "time": n("statTimePlayed"), "goals": [0] * n("statGoals"), "assists": [0] * n("statAssists"),
            "conceeded": [0] * n("statConceeded"), "yellow_cards": [0] * n("statYellow"),
            "red_card": [0] * n("statRed"), "own_goals": [0] * n("statOwnGoal"),
            "penalty_saved": [0] * n("statPenaltySave"), "penalty_miss": [0] * n("statPenaltyMiss"),
            "saves": n("statSaves"), "skillIndex": n("statSkillBonus"),
            "duelWon": n("statDuelWon"), "duelLost": n("statDuelLost"), "ballRecovery": n("statBallRecovery"),
            "headClearance": n("statHeadClearance"), "interception": n("statInterception"),
            "shotOffTarget": n("statShotOffTarget"), "errorLeadToGoal": n("statErrorLeadToGoal"),
        }
        pos = POS.get(row.get("positionId"), "?")
        drivers = r.pro_drivers(pos, detail, row.get("total"))
        adj = sum(d["points"] for d in drivers if d["label"] == "game adjustment")
        ok[(pos, adj)] += 1
        if adj and len(bad) < 25:
            bad.append((week, pos, row.get("total"), json.dumps(detail, separators=(",", ":")), drivers))
print("ADJ", sorted(ok.items()))
for b in bad:
    print("MISS", b)

cfg = json.load(open(r.CONFIG))["proleague"]
for t in cfg["teams"]:
    payload = r.get(f"{r.PRO}/team/{t['id']}/points/8?{r.PRO_Q}", headers=headers)
    for p in payload.get("players") or []:
        for s in p.get("stats") or []:
            if s.get("weekId") == 8:
                print("LIVE", p.get("short"), "points", s.get("points"), "value", s.get("value"))

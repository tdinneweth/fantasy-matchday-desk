#!/usr/bin/env python3
"""One-off: find what the players-stats total carries beyond its named fields."""
import json
from collections import Counter, defaultdict
import refresh as r

headers = {"Authorization": f"Bearer {r.pro_token()}"}
F = ["goals", "ownGoal", "penaltyGoals", "penaltySave", "penaltyMiss", "strokeGoals", "awards",
     "playedUpTo60Min", "playedMoreThan60Min", "threeOrFourGoalsAgainst", "fiveOrMoreGoalsAgainst",
     "inStarting", "assists", "yellow", "green", "red", "cleanSheet", "conceeded", "halfTime",
     "teamResultPoints", "MotM", "skillBonus", "bigChanceCreated", "headClearance", "ballRecovery",
     "duels", "interception", "dispossessed", "shotOffTarget", "errorLeadToGoal", "saves"]
CAND = ["statDispossessed", "statShotOffTarget", "statSaves", "statConceeded", "statDuelLost",
        "statDuelWon", "statBallRecovery", "statInterception", "statHeadClearance", "statTimePlayed",
        "statYellow", "statSkillBonus", "statBigChanceCreated", "statErrorLeadToGoal", "statTeamPrestatie",
        "statPerformancePoints", "statMatchPlayed", "statInStarting", "statGoals"]
diffs = Counter()
by = defaultdict(Counter)
rows_all = []
for week in (6, 7):
    rows = r.get(f"{r.PRO}/players-stats?{r.PRO_Q}&weekId={week}&pageNumber=1&pageRecords=800",
                 headers=headers).get("data") or []
    for row in rows:
        d = (row.get("total") or 0) - sum(row.get(f) or 0 for f in F)
        diffs[(row.get("positionId"), d)] += 1
        for c in CAND:
            by[c][(row.get("positionId"), row.get(c), d)] += 1
        rows_all.append(row)
print("DIFF", sorted(diffs.items()))
for c in CAND:
    print("BY", c, " | ".join("p%s %s=%s d%s x%d" % (k[0], c[4:], k[1], k[2], n)
                             for k, n in sorted(by[c].items(), key=lambda kv: (kv[0][0] or 0, str(kv[0][1]), kv[0][2]))))
for pos in (1, 2, 3, 4):
    for f, s in (("ballRecovery", "statBallRecovery"), ("headClearance", "statHeadClearance"), ("interception", "statInterception"), ("dispossessed", "statDispossessed"), ("shotOffTarget", "statShotOffTarget"), ("saves", "statSaves")):
        m = Counter((row.get(s), row.get(f)) for row in rows_all if row.get("positionId") == pos)
        print("MAP", pos, f, sorted(m.items(), key=lambda kv: (kv[0][0] or 0)))
    m = Counter(((row.get("statDuelWon") or 0) - (row.get("statDuelLost") or 0), row.get("duels")) for row in rows_all if row.get("positionId") == pos)
    print("MAP", pos, "duels(won-lost)", sorted(m.items()))
# one team record vs players-stats for the same player and week, to see which total the game credits
cfg = json.load(open(r.CONFIG))["proleague"]
ps = {(row.get("playerId"), row.get("weekId")): row for row in rows_all}
for t in cfg["teams"]:
    for week in (6, 7):
        payload = r.get(f"{r.PRO}/team/{t['id']}/points/{week}?{r.PRO_Q}", headers=headers)
        for p in payload.get("players") or []:
            for s in p.get("stats") or []:
                if s.get("weekId") != week:
                    continue
                row = ps.get((p.get("id"), week))
                if row:
                    print("CMP", week, p.get("short"), "teamPts", s.get("points"), "psTotal", row.get("total"),
                          "psSum", sum(row.get(f) or 0 for f in F), "corr", json.dumps(s.get("corrections")),
                          "val", s.get("value"))

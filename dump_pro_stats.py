#!/usr/bin/env python3
"""One-off: print the raw Pro League stat records for our squads."""
import json
import refresh as r

cfg = json.load(open(r.CONFIG))["proleague"]
headers = {"Authorization": f"Bearer {r.pro_token()}"}
for week in (7, 8):
    for t in cfg["teams"]:
        payload = r.get(f"{r.PRO}/team/{t['id']}/points/{week}?{r.PRO_Q}", headers=headers)
        for p in (payload.get("players") or [])[:15]:
            for s in p.get("stats") or []:
                if s.get("weekId") != week:
                    continue
                meta = {k: v for k, v in s.items() if k != "value"}
                print("TEAMSTAT", week, p.get("short"), p.get("positionId"), json.dumps(meta), s.get("value"))
    rows = r.get(f"{r.PRO}/players-stats?{r.PRO_Q}&weekId={week}&pageNumber=1&pageRecords=800",
                 headers=headers).get("data") or []
    print("PLAYERSTATS", week, len(rows))
    for row in rows[:6]:
        print("PSROW", week, json.dumps(row))

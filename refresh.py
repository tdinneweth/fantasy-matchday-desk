#!/usr/bin/env python3
"""Collect live points for the four fantasy teams and emit one JSON state doc.

Network goes through curl on purpose: the TLS proxy on this Mac breaks
urllib/requests.

Usage:
    ./refresh.py            # write state.json, print a one-line summary
    ./refresh.py --gate     # same, but print NOOP and skip writing when nothing is live
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "config.json")
STATE = os.path.join(HERE, "state.json")
EVENTS = os.path.join(HERE, "events.json")
RANKS = os.path.join(HERE, "ranks-history.json")
CACHE = os.path.join(HERE, ".cache")

FPL = "https://fantasy.premierleague.com/api"
PRO = "https://proleague.code.brussels"
PRO_Q = "competitionFeed=JPL&seasonId=2027"

POS = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD", 5: "MNG"}


def get(url, headers=None, cache_seconds=0):
    """GET json via curl, with an optional on-disk cache."""
    key = None
    if cache_seconds:
        os.makedirs(CACHE, exist_ok=True)
        key = os.path.join(CACHE, str(abs(hash(url))) + ".json")
        if os.path.exists(key) and time.time() - os.path.getmtime(key) < cache_seconds:
            with open(key) as fh:
                return json.load(fh)

    cmd = ["curl", "-sS", "-m", "30", "--compressed"]
    for k, v in (headers or {}).items():
        cmd += ["-H", f"{k}: {v}"]
    cmd.append(url)
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"curl failed for {url}: {out.stderr.strip()}")
    data = json.loads(out.stdout)

    if key:
        with open(key, "w") as fh:
            json.dump(data, fh)
    return data


def delta_of(rows, field):
    """Movement between the last two gameweeks that carry `field`.
    A positive delta means the rank number fell, i.e. you climbed."""
    ranked = [r for r in rows if r.get(field)]
    if len(ranked) < 2:
        return None
    prev, now = ranked[-2], ranked[-1]
    return {
        "from": prev[field],
        "to": now[field],
        "delta": prev[field] - now[field],
        "basis": "GW%s" % prev["event"],
    }


def remember_rank(team_id, week, rank):
    """The Pro League feed has no overall-rank history, so keep our own.
    Returns the movement against the most recent earlier week on record."""
    if not rank or not week:
        return None
    book = {}
    if os.path.exists(RANKS):
        try:
            book = json.load(open(RANKS))
        except ValueError:
            book = {}

    key = str(team_id)
    weeks = book.setdefault(key, {})
    earlier = [int(w) for w in weeks if int(w) < int(week)]
    move = None
    if earlier:
        prev_week = max(earlier)
        prev_rank = weeks[str(prev_week)]
        move = {
            "from": prev_rank,
            "to": rank,
            "delta": prev_rank - rank,
            "basis": "week %s" % prev_week,
        }

    weeks[str(week)] = rank
    with open(RANKS, "w") as fh:
        json.dump(book, fh, indent=1, sort_keys=True)
    return move


# --------------------------------------------------------------------------
# Fantasy Premier League
# --------------------------------------------------------------------------

def fixture_state(fx):
    """Verified against the live feed: bonus is already inside total_points while a
    match is in play, so nothing here needs to re-derive it from bps."""
    if fx is None:
        return "blank"
    if fx.get("finished") or fx.get("finished_provisional"):
        return "done"
    if fx.get("started"):
        return "live"
    return "upcoming"


def fpl_team(entry, label, boot, live, fixtures, gw):
    elements = {e["id"]: e for e in boot["elements"]}
    clubs = {t["id"]: t for t in boot["teams"]}
    livemap = {e["id"]: e for e in live["elements"]}
    fixmap = {f["id"]: f for f in fixtures}

    meta = get(f"{FPL}/entry/{entry}/", cache_seconds=600)
    picks = get(f"{FPL}/entry/{entry}/event/{gw}/picks/")

    squad, live_total, bench_total = [], 0, 0
    for p in picks["picks"]:
        el = elements[p["element"]]
        lv = livemap.get(p["element"], {})
        stats = lv.get("stats", {})
        pts = stats.get("total_points", 0)

        club = clubs[el["team"]]
        my_fixtures = [
            fixmap[ex["fixture"]] for ex in lv.get("explain", []) if ex.get("fixture") in fixmap
        ]
        upcoming = [f for f in fixtures if el["team"] in (f["team_h"], f["team_a"])]
        fx = my_fixtures[0] if my_fixtures else (upcoming[0] if upcoming else None)

        state = fixture_state(fx)

        opponent = ""
        if fx:
            home = fx["team_h"] == el["team"]
            other = fx["team_a"] if home else fx["team_h"]
            opponent = clubs[other]["short_name"] + (" (H)" if home else " (A)")

        score = minute = None
        if fx and (fx.get("started") or fx.get("finished")):
            score = "%s-%s" % (fx.get("team_h_score"), fx.get("team_a_score"))
            minute = fx.get("minutes")

        credit = {}
        for ex in lv.get("explain", []):
            for st in ex.get("stats", []):
                credit[st["identifier"]] = credit.get(st["identifier"], 0) + st.get("points", 0)

        bench = p["position"] > 11
        row = {
            "id": el["id"],
            "credit": credit,
            "name": el["web_name"],
            "photo": "fpl-%s.png" % el["code"],
            "score": score,
            "matchMinute": minute,
            "pos": POS.get(el["element_type"], "?"),
            "club": club["short_name"],
            "opponent": opponent,
            "points": pts,
            "bonus": stats.get("bonus", 0),
            "multiplier": p["multiplier"],
            "captain": p["is_captain"],
            "vice": p["is_vice_captain"],
            "bench": bench,
            "minutes": stats.get("minutes", 0),
            "state": state,
            "kickoff": (fx or {}).get("kickoff_time"),
            "goals": stats.get("goals_scored", 0),
            "assists": stats.get("assists", 0),
            "cleanSheet": bool(stats.get("clean_sheets", 0)),
            "yellow": stats.get("yellow_cards", 0),
            "red": stats.get("red_cards", 0),
            "ownGoals": stats.get("own_goals", 0),
            "penaltySaves": stats.get("penalties_saved", 0),
            "penaltyMisses": stats.get("penalties_missed", 0),
            "bps": stats.get("bps", 0),
        }
        squad.append(row)
        if bench:
            bench_total += pts
        else:
            live_total += pts * p["multiplier"]

    hist = picks.get("entry_history", {})
    hit = hist.get("event_transfers_cost", 0)

    overall_move = week_move = None
    try:
        rows = get(f"{FPL}/entry/{entry}/history/", cache_seconds=300).get("current") or []
        overall_move = delta_of(rows, "overall_rank")
        week_move = delta_of(rows, "rank")
    except Exception:
        pass
    return {
        "game": "FPL",
        "id": entry,
        "name": meta.get("name", label),
        "manager": f"{meta.get('player_first_name','')} {meta.get('player_last_name','')}".strip(),
        "gwPoints": live_total - hit,
        "hit": hit,
        "benchPoints": bench_total,
        "totalPoints": meta.get("summary_overall_points", 0),
        "overallRank": (overall_move or {}).get("to") or meta.get("summary_overall_rank"),
        "gwRank": (week_move or {}).get("to") or hist.get("rank"),
        "overallMove": overall_move,
        "weekMove": week_move,
        "chip": picks.get("active_chip"),
        "transfers": hist.get("event_transfers", 0),
        "autoSubs": len(picks.get("automatic_subs") or []),
        "squad": squad,
        "playersPlayed": sum(1 for r in squad if not r["bench"] and r["state"] == "done"),
        "playersLive": sum(1 for r in squad if not r["bench"] and r["state"] == "live"),
        "playersLeft": sum(1 for r in squad if not r["bench"] and r["state"] == "upcoming"),
    }


def fpl_block(cfg):
    boot = get(f"{FPL}/bootstrap-static/", cache_seconds=600)
    events = boot["events"]
    cur = next((e for e in events if e.get("is_current")), None)
    if cur is None:
        cur = next((e for e in events if e.get("is_next")), events[0])
    gw = cur["id"]

    live = get(f"{FPL}/event/{gw}/live/")
    fixtures = get(f"{FPL}/fixtures/?event={gw}")
    clubs = {t["id"]: t["short_name"] for t in boot["teams"]}

    matches = [
        {
            "home": clubs[f["team_h"]],
            "away": clubs[f["team_a"]],
            "homeGoals": f.get("team_h_score"),
            "awayGoals": f.get("team_a_score"),
            "minutes": f.get("minutes", 0),
            "started": bool(f.get("started")),
            "finished": bool(f.get("finished") or f.get("finished_provisional")),
            "kickoff": f.get("kickoff_time"),
        }
        for f in sorted(fixtures, key=lambda f: f.get("kickoff_time") or "")
    ]

    teams = [fpl_team(t["entry"], t.get("label", ""), boot, live, fixtures, gw) for t in cfg]
    return {
        "gw": gw,
        "name": cur["name"],
        "deadline": cur.get("deadline_time"),
        "finished": bool(cur.get("finished")),
        "average": cur.get("average_entry_score"),
        "highest": cur.get("highest_score"),
        "matches": matches,
        "teams": teams,
        "anyLive": any(m["started"] and not m["finished"] for m in matches),
    }


# --------------------------------------------------------------------------
# Fantasy Pro League (Fan Arena backend)
# --------------------------------------------------------------------------

def pro_token():
    """Session token comes from the environment in CI, otherwise from the login
    keychain. Never from the repo."""
    from_env = os.environ.get("PROLEAGUE_TOKEN", "").strip()
    if from_env:
        return from_env
    out = subprocess.run(
        ["security", "find-generic-password", "-a", os.environ.get("USER", ""),
         "-s", "fantasy-proleague-token", "-w"],
        capture_output=True, text=True)
    return out.stdout.strip() if out.returncode == 0 else ""


def pro_matches(week):
    """Public endpoint. `final`: absent = not kicked off, 0 = in play,
    1 = played awaiting confirmation, 2 = confirmed."""
    payload = get(f"{PRO}/matches?{PRO_Q}&weekId={week}", cache_seconds=60)
    rows = payload.get("matches", []) if isinstance(payload, dict) else (payload or [])
    now = datetime.now(timezone.utc)
    out = []
    for m in rows:
        final = m.get("final")
        kickoff = m.get("date")
        started = False
        if kickoff:
            try:
                started = datetime.fromisoformat(kickoff.replace("Z", "+00:00")) <= now
            except ValueError:
                started = False
        finished = final is not None and final >= 1
        out.append({
            "home": (m.get("homeId") or {}).get("short", "?"),
            "away": (m.get("awayId") or {}).get("short", "?"),
            "homeGoals": m.get("homeScore") if (started or finished) else None,
            "awayGoals": m.get("awayScore") if (started or finished) else None,
            "started": started or finished,
            "finished": finished,
            "kickoff": kickoff,
        })
    return out


def pro_team(cfg, week, headers, clubs):
    """Everything comes from team/{id}/points/{week} — it carries the team record,
    the week's lineup and every player's stats, and it answers for teams the
    account does not own (plain team/{id} does not)."""
    tid = cfg["id"]
    payload = get(f"{PRO}/team/{tid}/points/{week}?{PRO_Q}", headers=headers)
    team = payload.get("team") or {}

    # lineup for this week: roster.players is indexed by week number
    lineup = {}
    roster = (team.get("roster") or [{}])[0].get("players") or []
    if week < len(roster):
        for slot in roster[week] or []:
            lineup[slot.get("id")] = slot

    squad = []
    for p in payload.get("players") or []:
        slot = lineup.get(p.get("id"), {})
        stat = next((s for s in (p.get("stats") or []) if s.get("weekId") == week), None)
        detail = {}
        if stat and stat.get("value"):
            try:
                detail = json.loads(stat["value"])
            except (ValueError, TypeError):
                detail = {}

        cap = slot.get("cap", 0)
        portrait = p.get("portraitUrl") or ""
        squad.append({
            "id": p.get("id"),
            "credit": {},
            "minuteLog": {
                "goal": detail.get("goals") or [],
                "assist": detail.get("assists") or [],
                "yellow": detail.get("yellow_cards") or [],
                "red": detail.get("red_card") or [],
                "ownGoal": detail.get("own_goals") or [],
                "penaltySave": detail.get("penalty_saved") or [],
                "penaltyMiss": detail.get("penalty_miss") or [],
            },
            "name": p.get("short") or p.get("name") or "?",
            "photo": ("pro-%s.png" % p.get("id")) if portrait and "dummy" not in portrait else None,
            "photoSource": portrait if "dummy" not in portrait else None,
            "pos": {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}.get(p.get("positionId"), "?"),
            "club": clubs.get(p.get("clubId") or detail.get("club_id"), ""),
            "opponent": "",
            "points": (stat or {}).get("points", 0) or 0,
            "bonus": 0,
            "multiplier": 2 if cap == 1 else 1,
            "captain": cap == 1,
            "vice": cap == 2,
            "bench": slot.get("pos", 0) == 0,
            "minutes": detail.get("time", 0) or 0,
            "state": "done" if stat else "upcoming",
            "goals": len(detail.get("goals") or []),
            "assists": len(detail.get("assists") or []),
            "cleanSheet": bool(detail.get("time")) and not (detail.get("conceeded") or []),
            "yellow": len(detail.get("yellow_cards") or []),
            "red": len(detail.get("red_card") or []),
            "ownGoals": len(detail.get("own_goals") or []),
            "penaltySaves": len(detail.get("penalty_saved") or []),
            "penaltyMisses": len(detail.get("penalty_miss") or []),
            "bps": 0,
        })

    # order the way the game shows it: keepers first, bench last
    order = {"GK": 0, "DEF": 1, "MID": 2, "FWD": 3, "?": 4}
    squad.sort(key=lambda s: (s["bench"], order[s["pos"]]))

    stats = payload.get("weekStat") or []
    wk = next((s for s in stats if s.get("weekId") == week), stats[0] if stats else {})
    starters = [s for s in squad if not s["bench"]]

    # the feed carries no overall-rank history, but each week's own rank is
    # retrievable a week at a time
    week_move = None
    if week > 1 and wk.get("rank"):
        try:
            prev = get(f"{PRO}/team/{tid}/points/{week - 1}?{PRO_Q}",
                       headers=headers, cache_seconds=1800)
            pstats = prev.get("weekStat") or []
            pwk = next((s for s in pstats if s.get("weekId") == week - 1), None)
            if pwk and pwk.get("rank"):
                week_move = {
                    "from": pwk["rank"],
                    "to": wk["rank"],
                    "delta": pwk["rank"] - wk["rank"],
                    "basis": "week %s" % (week - 1),
                }
        except Exception:
            week_move = None

    return {
        "game": "PRO",
        "id": tid,
        "name": team.get("name") or cfg.get("label", "?"),
        "gwPoints": wk.get("points"),
        "gwRank": wk.get("rank"),
        "weekMove": week_move,
        "overallMove": remember_rank(tid, week, team.get("rank")),
        "totalPoints": team.get("points"),
        "overallRank": team.get("rank"),
        "benchPoints": sum(s["points"] for s in squad if s["bench"]),
        "transfers": team.get("transfers", 0),
        "chip": next((c for c in ("tripleCaptain", "freeHit", "wildCard")
                      if team.get(c) == week), None),
        "squad": squad,
        "playersPlayed": sum(1 for s in starters if s["minutes"]),
        "playersLive": 0,
        "playersLeft": sum(1 for s in starters if not s["minutes"]),
    }


def pro_block(cfg):
    teams_cfg = (cfg or {}).get("teams") or []
    if not teams_cfg:
        return None

    info = get(f"{PRO}/matches/deadline-info?{PRO_Q}", cache_seconds=300)
    week = info["deadlineInfo"]["displayWeek"]
    out = {"week": week, "deadline": info["deadlineInfo"].get("deadlineDate"),
           "teams": [], "matches": []}

    try:
        out["matches"] = pro_matches(week)
    except Exception as exc:
        out["matchError"] = str(exc)

    token = (cfg or {}).get("token") or pro_token()
    if not token:
        out["error"] = "no session token"
        out["teams"] = [
            {"game": "PRO", "id": t.get("id"), "name": t.get("label", "?"), "gwPoints": None,
             "totalPoints": None, "squad": [], "unavailable": True}
            for t in teams_cfg
        ]
        return out

    headers = {"Authorization": f"Bearer {token}"}
    try:
        clubs = {c["id"]: c["short"] for c in get(f"{PRO}/clubs?{PRO_Q}", cache_seconds=3600)["clubs"]}
    except Exception:
        clubs = {}

    # what each club is doing this week, so every player row can name an opponent
    context = {}
    for m in out["matches"]:
        state = "done" if m["finished"] else ("live" if m["started"] else "upcoming")
        score = None
        if m["homeGoals"] is not None:
            score = "%s-%s" % (m["homeGoals"], m["awayGoals"])
        context[m["home"]] = {"opponent": m["away"] + " (H)", "state": state,
                              "kickoff": m["kickoff"], "score": score}
        context[m["away"]] = {"opponent": m["home"] + " (A)", "state": state,
                              "kickoff": m["kickoff"], "score": score}

    for t in teams_cfg:
        try:
            row = pro_team(t, week, headers, clubs)
            for s in row["squad"]:
                ctx = context.get(s["club"])
                if ctx:
                    s["opponent"] = ctx["opponent"]
                    s["kickoff"] = ctx["kickoff"]
                    s["state"] = ctx["state"]
                    s["score"] = ctx["score"]
            starters = [s for s in row["squad"] if not s["bench"]]
            row["playersLive"] = sum(1 for s in starters if s["state"] == "live")
            row["playersPlayed"] = sum(1 for s in starters if s["state"] == "done")
            row["playersLeft"] = sum(1 for s in starters if s["state"] == "upcoming")
            out["teams"].append(row)
        except Exception as exc:
            out["teams"].append({
                "game": "PRO", "id": t.get("id"), "name": t.get("label", "?"),
                "gwPoints": None, "totalPoints": None, "squad": [],
                "unavailable": True, "error": str(exc),
            })
    return out



# --------------------------------------------------------------------------
# Match events that move my players' scores
# --------------------------------------------------------------------------

# what we watch, and how each reads in the ticker
KINDS = [
    ("goal", "goals", "goal", "goals_scored"),
    ("assist", "assists", "assist", "assists"),
    ("bonus", "bonus", "bonus point", "bonus"),
    ("yellow", "yellow", "yellow card", "yellow_cards"),
    ("red", "red", "red card", "red_cards"),
    ("ownGoal", "ownGoals", "own goal", "own_goals"),
    ("penaltySave", "penaltySaves", "penalty save", "penalties_saved"),
    ("penaltyMiss", "penaltyMisses", "penalty miss", "penalties_missed"),
]

# Fantasy Pro League scoring, from the official rules at
# https://fantasy.proleague.be/info/rules (section 2.1). The Pro League feed
# gives no per-event points, unlike FPL, so discrete events are priced here.
# Note the differences from FPL: a yellow is -2 and a red -4.
JPL_POINTS = {
    "goal": {"GK": 10, "DEF": 6, "MID": 5, "FWD": 4},
    "assist": 3,
    "yellow": -2,
    "red": -4,
    "ownGoal": -2,
    "penaltySave": 5,
    "penaltyMiss": -3,
    "bonus": 3,   # "prestatiebonus"
}


def track_events(state):
    """Diff this reading against the last one and log what changed.

    First run of a gameweek backfills whatever already happened, so the ticker
    is never empty; Pro League carries real minutes, FPL does not, so those are
    stamped with the match clock when spotted and left blank when backfilled.
    """
    gw = (state.get("fpl") or {}).get("gw")
    week = (state.get("pro") or {}).get("week")
    key = "gw%s-wk%s" % (gw, week)

    book = {"key": key, "counters": {}, "log": []}
    if os.path.exists(EVENTS):
        try:
            loaded = json.load(open(EVENTS))
            if loaded.get("key") == key:
                book = loaded
        except ValueError:
            pass

    # Entries logged before events carried an absolute time fall back to their
    # detection timestamp, which is "now" for everything backfilled in one pass —
    # that floats a Friday goal above today's. Drop them; they re-derive below.
    book["log"] = [e for e in book["log"] if e.get("at")]

    first_run = not book["counters"]
    counters = book["counters"]
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # who owns whom, so an event can name the teams it moves
    owners = {}
    for t in state["fpl"]["teams"] + ((state.get("pro") or {}).get("teams") or []):
        for p in t.get("squad", []):
            owners.setdefault(player_key(t, p), []).append({
                "team": t["name"],
                "game": t["game"],
                "multiplier": p.get("multiplier", 1),
                "bench": p.get("bench", False),
            })

    seen, fresh = {}, []
    for t in state["fpl"]["teams"] + ((state.get("pro") or {}).get("teams") or []):
        for p in t.get("squad", []):
            k = player_key(t, p)
            if k in seen:
                continue
            seen[k] = True
            before = counters.get(k, {})
            after = {kind: count_of(p, field) for kind, field, _, _ in KINDS}
            counters[k] = after

            if before == after:
                continue
            for kind, field, label, identifier in KINDS:
                gained = after[kind] - before.get(kind, 0)
                if gained <= 0:
                    continue
                minutes = (p.get("minuteLog") or {}).get(kind) or []
                for i in range(gained):
                    index = before.get(kind, 0) + i
                    minute = (minutes[index] if index < len(minutes)
                              else (None if first_run else p.get("matchMinute")))
                    fresh.append({
                        "ts": now,
                        "at": happened_at(p.get("kickoff"), minute, now),
                        "backfilled": first_run,
                        "kind": kind,
                        "label": label if kind != "bonus" else
                                 ("%s bonus point%s" % (gained, "" if gained == 1 else "s")),
                        "player": p["name"],
                        "club": p.get("club", ""),
                        "photo": p.get("photo"),
                        "opponent": p.get("opponent", ""),
                        "score": p.get("score"),
                        "minute": minute,
                        "points": credit_for(t["game"], p, kind, identifier, after[kind],
                                             gained if kind == "bonus" else 1),
                        "teams": owners.get(k, []),
                    })
                    if kind == "bonus":
                        break  # one line for the whole bonus change

    log = fresh + book["log"]
    log.sort(key=lambda e: e.get("at") or e["ts"], reverse=True)
    book["log"] = log[:60]
    book["key"] = key
    with open(EVENTS, "w") as fh:
        json.dump(book, fh, indent=1)
    return book["log"]


def happened_at(kickoff, minute, fallback):
    """When an event actually occurred, in absolute time.

    Match minutes alone sort wrongly across matches that kicked off hours apart,
    so each event is placed at kickoff + minute. An event whose minute the feed
    does not publish sits at its own kickoff — the right neighbourhood, without
    inventing a minute it never gave us.
    """
    if not kickoff:
        return fallback
    try:
        start = datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
    except ValueError:
        return fallback
    return (start + timedelta(minutes=minute or 0)).isoformat(timespec="seconds")


def player_key(team, player):
    return "%s:%s" % (team["game"], player.get("id") or player["name"])


def count_of(player, field):
    if field == "bonus":
        return player.get("bonus", 0) or 0
    return player.get(field, 0) or 0


def credit_for(game, player, kind, identifier, total, gained):
    """FPL publishes points per stat in its `explain` block, so its events are
    priced from the feed itself. The Pro League publishes no such figure, so
    those come from the official rules table."""
    if game == "FPL":
        credit = player.get("credit") or {}
        if identifier not in credit or not total:
            return None
        if kind == "bonus":
            # a bonus point is worth exactly one point, so a climb from 1 to 2
            # is +1 — not the new total
            return gained
        return round(credit[identifier] / total) * gained

    value = JPL_POINTS.get(kind)
    if isinstance(value, dict):
        return value.get(player.get("pos"))
    return value


# --------------------------------------------------------------------------

def main():
    if not os.path.exists(CONFIG):
        print(f"missing {CONFIG} — copy config.example.json and fill in the ids", file=sys.stderr)
        return 2
    with open(CONFIG) as fh:
        cfg = json.load(fh)

    state = {
        "updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fpl": fpl_block([t for t in cfg.get("fpl", []) if t.get("entry")]),
        "pro": pro_block(cfg.get("proleague")),
    }

    try:
        state["ticker"] = track_events(state)
    except Exception as exc:
        state["ticker"] = []
        state["tickerError"] = str(exc)

    live = state["fpl"]["anyLive"] or any(
        m.get("started") and not m.get("finished") for m in ((state["pro"] or {}).get("matches") or [])
    )
    state["live"] = live

    if "--gate" in sys.argv and not live:
        print("NOOP")
        return 0

    with open(STATE, "w") as fh:
        json.dump(state, fh, indent=1)

    rows = state["fpl"]["teams"] + ((state["pro"] or {}).get("teams") or [])
    summary = ", ".join(f"{t['name']}: {t['gwPoints']}" for t in rows)
    print(f"{'LIVE' if live else 'IDLE'} {STATE} | {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

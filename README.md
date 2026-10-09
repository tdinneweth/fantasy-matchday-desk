# Fantasy Matchday Desk

Live gameweek points for four fantasy teams — two in the Fantasy Premier League,
two in the Belgian Fantasy Pro League — on one page, refreshed while matches are on.

- `refresh.py` — collects a reading from both games into `state.json`: live points,
  squads, fixtures, the point ticker, and per team the season history (points and
  rank per round), every transfer, and squad value
- `build.py` — bakes the newest reading into the page. `--standalone` builds the
  hosted page, which loads portraits and crests from the games' own image hosts
- `photos.py` — pulls each squad's portraits for the artifact build only, whose
  CSP blocks remote images so `build.py` inlines them

GitHub Actions runs the collector on a schedule and pushes each reading to the
`data` branch; the published page reads it from there, so nothing needs to run
locally.

## Running it yourself

    ./refresh.py && ./build.py && open dashboard.html

Fantasy Pro League needs a session token (`PROLEAGUE_TOKEN`, or a
`fantasy-proleague-token` entry in the macOS login keychain). The Premier League
half needs nothing — that API is public per team id.

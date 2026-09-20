# Fantasy Matchday Desk

Live gameweek points for four fantasy teams — two in the Fantasy Premier League,
two in the Belgian Fantasy Pro League — on one page, refreshed while matches are on.

- `refresh.py` — collects a reading from both games into `state.json`
- `photos.py` — pulls each squad's official player portraits
- `build.py` — inlines the newest reading and the portraits into `dashboard.html`

GitHub Actions runs the collector on a schedule and pushes each reading to the
`data` branch; the published page reads it from there, so nothing needs to run
locally.

## Running it yourself

    ./refresh.py && ./build.py && open dashboard.html

Fantasy Pro League needs a session token (`PROLEAGUE_TOKEN`, or a
`fantasy-proleague-token` entry in the macOS login keychain). The Premier League
half needs nothing — that API is public per team id.

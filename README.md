# College Football Play Sleuth

A small locally hosted app that queries college-football play-by-play from the
CollegeFootballData (CFBD) API: any play type (or OR-group of types), an
optional yardage floor, and an optional penalty-only view that attributes each
penalty to the offense or defense. All CFBD requests happen on the server; the
API key never reaches the browser.

## Setup

1. Get a CFBD key: https://collegefootballdata.com/key (new keys can take a few
   minutes to activate).
2. Add it to a local env file:
   ```
   cp .env.example .env
   # edit .env and paste your key
   ```
3. Install dependencies (a virtualenv is recommended):
   ```
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   ```

## Run

```
uvicorn server.main:app --reload --port 8000
```

Then open http://localhost:8000 — pick year / week / season / division, pick
one or more play types (or leave the list untouched from its default, or clear
it for "any type"), optionally set a minimum yards-gained and/or the
penalty-only toggle, and hit **Run query**. **Download CSV** exports the same
result.

Note: CFBD gives FBS its own **week 0** for the season-opening slate in late
August, so week is allowed down to 0 (not 1).

## How it works

- `server/cfbd_client.py` pulls `/plays` for a week and caches the raw JSON to
  `cache/` (data is immutable once games are final). It also pulls and caches
  CFBD's authoritative play-type vocabulary from `/plays/types`, which powers
  the play-type picker in the UI.
- **CFBD's server-side `playType` filter on `/plays` does not reliably work**
  (confirmed: it returned 0 rows for `Penalty` in a week where 943 existed) —
  so `get_plays()` always pulls the full week and every filter in this app runs
  locally against that data.
- `server/filters.py` (`run_query`) is a general predicate filter: keep a play
  if its type is in the requested OR-group (or keep any type if none given),
  keep it only if `yardsGained >= min_yards` (if set), and — when
  `penalty_only` is set — keep it only if its text shows a penalty, attributing
  that penalty to the offense or defense.
- `scripts/cfbd_explore.py` is a standalone, no-dependency exploration script
  (not part of the running app) for checking CFBD's vocabulary, raw field
  names, and play counts before changing filters.

### Endpoints

- `GET /api/play-types` — the raw CFBD play-type vocabulary (id/text/abbreviation).
- `GET /api/query` — `year`, `week`, `season_type`, `classification`, repeated
  `play_type`, `min_yards`, `penalty_only`. Returns `{results, summary}` (summary
  only present when `penalty_only=true`).
- `GET /api/query.csv` — same params, streams a CSV download.

## Known rough edges

- `penalized_side()` reads the team named right before "Penalty" in the play
  text (CFBD's wording is `"<Team> Penalty, <foul> ..."`, e.g. `"Kansas
  Penalty, Offensive Holding (Brendan Leal) to the WAG 31"`). That depends on
  CFBD's exact wording, so anything it can't confidently attribute lands in an
  **Unattributed** bucket rather than being guessed. After a real pull, check
  that bucket — if legitimate fouls show up there, widen the matching (e.g.
  handle team abbreviations) in `filters.py`.
- CFBD also emits penalties as their own standalone play (`playType ==
  "Penalty"`) instead of embedded in another play's text — but those rows
  aren't reliably linked to whichever play type follows in the same drive (a
  false start or delay of game can occur several plays before an unrelated
  punt). So `penalty_only` only counts penalties embedded in the selected play
  type's own text, not nearby standalone `Penalty` plays.
- `yardsGained` on a play can include yardage from a penalty enforced on that
  same play, so a `min_yards` filter can occasionally include a play whose
  actual run/catch/etc. gained less than the threshold before the penalty was
  applied.

## Corporate network note

If you're behind a TLS-inspecting corporate proxy, plain `httpx`/`urllib`
requests to CFBD will fail with `CERTIFICATE_VERIFY_FAILED` because the
intercepting root CA isn't in the bundled `certifi` trust store (it is trusted
by Windows, though). `server/cfbd_client.py` works around this with the
`truststore` package, which points `httpx` at the OS trust store instead.

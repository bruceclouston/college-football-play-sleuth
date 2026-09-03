#!/usr/bin/env python3
"""Explore CFBD play data before wiring play-type filters into the app.

Three jobs:
  1. Print the authoritative play-type vocabulary (from CFBD, not guesses).
  2. Print one raw play so you can confirm exact field names/casing.
  3. Answer the core question: which games contain a given play type
     (optionally over a yardage threshold, over a week range).

No pip install needed — uses only the standard library.

Setup: put CFBD_API_KEY in the environment or a .env file next to this script.

Examples:
  python cfbd_explore.py --types
  python cfbd_explore.py --sample --year 2026 --week 1 --division fbs
  python cfbd_explore.py --games "Pass Reception" --min-yards 50 \
      --year 2026 --weeks 1-2 --division fbs
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://api.collegefootballdata.com"


def load_key() -> str:
    key = os.getenv("CFBD_API_KEY")
    if not key:
        envpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        if os.path.exists(envpath):
            for line in open(envpath):
                line = line.strip()
                if line.startswith("CFBD_API_KEY") and "=" in line:
                    key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    if not key:
        sys.exit("No CFBD_API_KEY found (set it in the environment or a .env file).")
    return key


def api_get(path: str, params: dict | None = None):
    url = BASE + path
    if params:
        clean = {k: v for k, v in params.items() if v is not None}
        url += "?" + urllib.parse.urlencode(clean)
    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {KEY}", "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 401:
            sys.exit("401 Unauthorized — check your key. New keys take a few "
                     "minutes to activate.")
        sys.exit(f"HTTP {e.code}: {e.read().decode()[:300]}")


def parse_weeks(s: str) -> list[int]:
    if "-" in s:
        a, b = s.split("-")
        return list(range(int(a), int(b) + 1))
    return [int(s)]


def cmd_types():
    """The authoritative vocabulary. Build the app's play_type groups from THIS."""
    types = api_get("/plays/types")
    print(f"{len(types)} play types (id / text / abbreviation):\n")
    for t in sorted(types, key=lambda x: x.get("id", 0)):
        print(f'  {str(t.get("id")):>4}  {t.get("text"):<28} {t.get("abbreviation", "")}')


def cmd_sample(year, week, season_type, division):
    """Dump one raw play so you can confirm exact field names before filtering on them.
    Watch for: play_type vs playType, yards_gained vs yardsGained, home/away, offense/defense."""
    plays = api_get("/plays", {"year": year, "week": week,
                               "seasonType": season_type, "classification": division})
    if not plays:
        print("No plays returned for those params.")
        return
    print("First play (confirm these field names in the app):\n")
    print(json.dumps(plays[0], indent=2))


def cmd_games(play_type, year, weeks, season_type, division, min_yards):
    """Which games contain this play type. This IS the original ask, answered live.
    Note: server-side playType filtering is exact — e.g. 'Pass Reception' will not
    include caught touchdowns typed as 'Passing Touchdown'. Run --types first, then
    query each relevant type. The yardage threshold is applied locally."""
    per_game = {}
    scanned = 0
    for wk in parse_weeks(weeks):
        plays = api_get("/plays", {"year": year, "week": wk,
                                   "seasonType": season_type,
                                   "classification": division,
                                   "playType": play_type})
        for p in plays:
            if min_yards is not None:
                yg = p.get("yards_gained")
                if yg is None or yg < min_yards:
                    continue
            scanned += 1
            game = f'{p.get("away")} @ {p.get("home")}'
            per_game[game] = per_game.get(game, 0) + 1

    label = f'"{play_type}"'
    if min_yards is not None:
        label += f" with yards_gained >= {min_yards}"
    print(f'{label}  |  {year} {season_type} {division}, weeks {weeks}')
    print(f"{scanned} matching plays across {len(per_game)} games:\n")
    for game, n in sorted(per_game.items(), key=lambda kv: -kv[1]):
        print(f"  {n:>3}  {game}")
    if scanned == 0:
        print("  (none — if you expected hits, confirm the play_type string via --types,\n"
              "   and confirm the yards field name via --sample)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Explore CFBD play-by-play data.")
    ap.add_argument("--types", action="store_true", help="list the play-type vocabulary")
    ap.add_argument("--sample", action="store_true", help="dump one raw play")
    ap.add_argument("--games", metavar="PLAY_TYPE", help="find games containing this play type")
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--week", type=int, default=1, help="single week (for --sample)")
    ap.add_argument("--weeks", default="1", help="week or range for --games, e.g. 1-4")
    ap.add_argument("--season-type", default="regular")
    ap.add_argument("--division", default="fbs", help="fbs or fcs")
    ap.add_argument("--min-yards", type=int, default=None, help="threshold on yards_gained")
    args = ap.parse_args()

    KEY = load_key()

    if args.types:
        cmd_types()
    elif args.sample:
        cmd_sample(args.year, args.week, args.season_type, args.division)
    elif args.games:
        cmd_games(args.games, args.year, args.weeks, args.season_type,
                  args.division, args.min_yards)
    else:
        ap.print_help()

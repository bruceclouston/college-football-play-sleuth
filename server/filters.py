"""General predicate query over a list of CFBD play objects, plus penalty
detection and team attribution.

`penalized_side()` reads the team named right before "Penalty" in the play
text (CFBD's actual wording is "<Team> Penalty, <foul> ... ", e.g. "Kansas
Penalty, Offensive Holding (Brendan Leal) to the WAG 31"). That depends on
CFBD's exact wording, so anything it can't confidently attribute lands in the
"unattributed" bucket rather than being guessed.

Note on standalone "Penalty" plays: CFBD also emits penalties as their own
play (playType == "Penalty") rather than embedded in another play's text, but
those rows aren't reliably linked to whichever play type follows in the same
drive — a false start or delay of game can show up several plays before an
unrelated punt. So a "penalties on play type X" query only counts penalties
embedded in an X-type play's own text, not nearby standalone Penalty plays.
"""

import re

# A team name is one or more capitalized tokens (or a parenthetical like
# "(OH)") directly preceding "Penalty". Requiring the whole run to be
# capitalized keeps it from swallowing the preceding clause, which normally
# ends in a lowercase word or a yard-line number.
_TOKEN = r"(?:[A-Z][\w&.'\-]*|\([A-Za-z.]+\))"
PENALTY_RE = re.compile(rf"((?:{_TOKEN}\s+)*{_TOKEN})\s+[Pp]enalty\b")


def _normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def has_penalty(play_text: str) -> bool:
    return "penalty" in (play_text or "").lower()


def penalized_side(play_text: str, offense: str, defense: str) -> str:
    match = PENALTY_RE.search(play_text or "")
    if not match:
        return "unattributed"

    captured = _normalize(match.group(1))
    if not captured:
        return "unattributed"

    offense_norm, defense_norm = _normalize(offense or ""), _normalize(defense or "")
    is_offense = bool(offense_norm) and (captured in offense_norm or offense_norm in captured)
    is_defense = bool(defense_norm) and (captured in defense_norm or defense_norm in captured)

    if is_offense and not is_defense:
        return "offense"
    if is_defense and not is_offense:
        return "defense"
    return "unattributed"


def format_clock(clock: dict | None) -> str | None:
    if not clock:
        return None
    minutes, seconds = clock.get("minutes"), clock.get("seconds")
    if minutes is None or seconds is None:
        return None
    return f"{minutes}:{seconds:02d}"


def run_query(
    plays: list[dict],
    play_types: list[str] | None,
    min_yards: int | None = None,
    penalty_only: bool = False,
) -> list[dict]:
    """Filter plays by an OR-group of play types plus optional predicates.

    - `play_types`: keep a play if its playType matches ANY of these
      (case-insensitive). None/empty means "any play type".
    - `min_yards`: keep a play only if yardsGained >= min_yards.
    - `penalty_only`: keep a play only if its text shows a penalty, and
      attribute that penalty to the offense/defense/unattributed.
    """
    type_set = {t.strip().lower() for t in play_types} if play_types else None
    results = []

    for play in plays:
        if type_set is not None and (play.get("playType") or "").strip().lower() not in type_set:
            continue

        if min_yards is not None:
            yards_gained = play.get("yardsGained")
            if yards_gained is None or yards_gained < min_yards:
                continue

        play_text = play.get("playText") or ""
        if penalty_only and not has_penalty(play_text):
            continue

        offense, defense = play.get("offense", ""), play.get("defense", "")
        row = {
            "period": play.get("period"),
            "clock": format_clock(play.get("clock")),
            "offense": offense,
            "defense": defense,
            "playType": play.get("playType"),
            "yardsGained": play.get("yardsGained"),
            "playText": play_text,
        }
        if penalty_only:
            row["penalizedSide"] = penalized_side(play_text, offense, defense)
        results.append(row)

    return results


def summarize_penalties(results: list[dict]) -> dict:
    summary = {"offense": 0, "defense": 0, "unattributed": 0}
    for row in results:
        side = row.get("penalizedSide")
        if side in summary:
            summary[side] += 1
    return summary

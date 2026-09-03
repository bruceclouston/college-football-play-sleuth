import csv
import io
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from server.cfbd_client import CFBDError, get_plays, get_play_types
from server.filters import run_query, summarize_penalties

load_dotenv()

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(title="College Football Play Sleuth")


def _run_query(
    year: int,
    week: int,
    season_type: str,
    classification: str | None,
    play_type: list[str] | None,
    min_yards: int | None,
    penalty_only: bool,
) -> list[dict]:
    try:
        plays = get_plays(year, week, season_type, classification)
    except CFBDError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return run_query(plays, play_type, min_yards, penalty_only)


@app.get("/api/play-types")
def api_play_types():
    try:
        return get_play_types()
    except CFBDError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/query")
def api_query(
    year: int = Query(..., ge=1869),
    week: int = Query(..., ge=0, le=20),
    season_type: str = Query("regular", pattern="^(regular|postseason)$"),
    classification: str | None = Query(None),
    play_type: list[str] | None = Query(None),
    min_yards: int | None = Query(None),
    penalty_only: bool = Query(False),
):
    results = _run_query(year, week, season_type, classification, play_type, min_yards, penalty_only)
    payload = {"results": results}
    if penalty_only:
        payload["summary"] = summarize_penalties(results)
    return payload


@app.get("/api/query.csv")
def api_query_csv(
    year: int = Query(..., ge=1869),
    week: int = Query(..., ge=0, le=20),
    season_type: str = Query("regular", pattern="^(regular|postseason)$"),
    classification: str | None = Query(None),
    play_type: list[str] | None = Query(None),
    min_yards: int | None = Query(None),
    penalty_only: bool = Query(False),
):
    results = _run_query(year, week, season_type, classification, play_type, min_yards, penalty_only)

    buffer = io.StringIO()
    fieldnames = ["period", "clock", "offense", "defense", "playType", "yardsGained", "playText"]
    if penalty_only:
        fieldnames.insert(-1, "penalizedSide")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(results)
    buffer.seek(0)

    types_slug = "-".join(t.replace(" ", "_") for t in (play_type or ["any"]))
    filename = f"plays_{year}_wk{week}_{types_slug}.csv"
    return StreamingResponse(
        buffer,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

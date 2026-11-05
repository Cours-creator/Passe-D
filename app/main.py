import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.selector import select_suggestions


BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
LOCAL_DIR = BASE_DIR / "data" / "local"


def load_data(data_dir=BASE_DIR / "data", local_dir=LOCAL_DIR):
    """Utilise la base réelle générée en local, sinon la démonstration fictive."""
    database_path = local_dir / "database.json"
    events_path = local_dir / "events.json"
    if not (database_path.exists() and events_path.exists()):
        database_path = data_dir / "demo_data.json"
        events_path = data_dir / "match_events.json"
    return (
        json.loads(database_path.read_text(encoding="utf-8")),
        json.loads(events_path.read_text(encoding="utf-8")),
    )


DATABASE, EVENTS = load_data()
MATCH = DATABASE["match"]
DATA_MODE = DATABASE.get("meta", {}).get("mode", "demo")

app = FastAPI(title="Passe D")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/data", StaticFiles(directory=BASE_DIR / "data"), name="data")


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
async def health():
    return {"status": "ok", "mode": DATA_MODE}


@app.get("/api/database")
async def database():
    return DATABASE


@app.get("/api/demo")
async def demo():
    teams = {team["id"]: team["name"] for team in DATABASE["teams"]}
    stadium = next(item for item in DATABASE["stadiums"] if item["id"] == MATCH["stadium_id"])
    return {
        "match": MATCH,
        "home_team": teams[MATCH["home_team_id"]],
        "away_team": teams[MATCH["away_team_id"]],
        "stadium": stadium["name"],
        "competition": MATCH["competition"],
        "mode": DATA_MODE,
    }


def _event_context(event):
    context = {
        **event,
        "match_id": MATCH["id"],
        "stadium_id": MATCH["stadium_id"],
    }
    if event.get("type") == "substitution":
        context["player_ids"] = [event["player_out_id"], event["player_in_id"]]
    return context


def _sse(event_name, payload):
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event_name}\ndata: {data}\n\n"


@app.get("/api/replay")
async def replay(request: Request):
    async def stream():
        yield _sse("started", {"total": len(EVENTS), "match_id": MATCH["id"]})
        shown = set()

        for index, event in enumerate(EVENTS):
            delay = max(0, float(event.get("delay_seconds", 1)))
            if delay >= 3:
                await asyncio.sleep(delay / 2)
                if await request.is_disconnected():
                    return
                calm_context = _event_context({"type": "calm", "team_id": event.get("team_id")})
                calm_suggestions = select_suggestions(calm_context, DATABASE, exclude=shown)
                shown.update(item["source_id"] for item in calm_suggestions)
                yield _sse(
                    "moment",
                    {
                        "kind": "calm",
                        "minute": event["minute"],
                        "second": event["second"],
                        "suggestions": calm_suggestions,
                    },
                )
                await asyncio.sleep(delay / 2)
            else:
                await asyncio.sleep(delay)

            if await request.is_disconnected():
                return
            context = _event_context(event)
            yield _sse(
                "moment",
                {
                    "kind": "event",
                    "event": event,
                    "suggestions": select_suggestions(context, DATABASE),
                },
            )

        yield _sse("finished", {"total": len(EVENTS)})

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
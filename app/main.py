import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.selector import select_suggestions


BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
DATABASE = json.loads((BASE_DIR / "data" / "demo_data.json").read_text(encoding="utf-8"))
EVENTS = json.loads((BASE_DIR / "data" / "match_events.json").read_text(encoding="utf-8"))
MATCH = DATABASE["match"]

app = FastAPI(title="Passe D · Démonstration")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
async def health():
    return {"status": "ok", "mode": "demo"}


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

        for index, event in enumerate(EVENTS):
            delay = max(0, float(event.get("delay_seconds", 1)))
            if delay >= 3:
                await asyncio.sleep(delay / 2)
                if await request.is_disconnected():
                    return
                calm_context = _event_context({"type": "calm", "team_id": event.get("team_id")})
                yield _sse(
                    "moment",
                    {
                        "kind": "calm",
                        "minute": event["minute"],
                        "second": event["second"],
                        "suggestions": select_suggestions(calm_context, DATABASE),
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
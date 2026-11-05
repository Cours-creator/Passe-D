"""Téléchargement et normalisation des données StatsBomb Open Data.

Le contrat StatsBomb interdit de redistribuer les données : tout ce que ce module
télécharge ou produit reste dans des dossiers locaux exclus de Git.
"""

import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BASE_URL = "https://raw.githubusercontent.com/statsbomb/open-data/master"
LOGO_URL = f"{BASE_URL}/img/SB%20-%20Icon%20Lockup%20-%20Colour%20positive.png"
USER_AGENT = "PasseD-prototype/0.1 (https://github.com/Cours-creator/Passe-D)"
SHOOTOUT_PERIOD = 5


def download(url, timeout=60):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def fetch_json(path, cache_dir, fetch=download):
    """Lit un fichier du dépôt StatsBomb, en passant par le cache local."""
    target = Path(cache_dir) / path
    if target.exists():
        return json.loads(target.read_text(encoding="utf-8"))
    payload = fetch(f"{BASE_URL}/{path}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    return json.loads(payload)


def _card_type(event):
    details = event.get("foul_committed") or event.get("bad_behaviour") or {}
    name = (details.get("card") or {}).get("name")
    if name == "Yellow Card":
        return "yellow_card", "Carton jaune"
    if name == "Second Yellow":
        return "red_card", "Deuxième carton jaune"
    if name == "Red Card":
        return "red_card", "Carton rouge"
    return None, None


def extract_key_events(raw_events):
    """Garde les événements utiles au commentaire, dans l'ordre du match."""
    key_events = []
    seen_periods = set()
    for event in sorted(raw_events, key=lambda item: item.get("index", 0)):
        kind = event.get("type", {}).get("name")
        base = {
            "period": event.get("period"),
            "minute": event.get("minute", 0),
            "second": event.get("second", 0),
            "team_id": event.get("team", {}).get("id"),
            "player_id": event.get("player", {}).get("id"),
            "player_name": event.get("player", {}).get("name"),
        }

        if kind in ("Half Start", "Half End"):
            marker = (kind, base["period"])
            if marker not in seen_periods:
                seen_periods.add(marker)
                label = "period_start" if kind == "Half Start" else "period_end"
                key_events.append({**base, "kind": label, "team_id": None, "player_id": None})
        elif kind == "Shot":
            shot = event.get("shot", {})
            scored = shot.get("outcome", {}).get("name") == "Goal"
            if base["period"] == SHOOTOUT_PERIOD:
                key_events.append({**base, "kind": "shootout", "scored": scored})
            elif scored:
                penalty = shot.get("type", {}).get("name") == "Penalty"
                key_events.append({**base, "kind": "goal", "penalty": penalty})
        elif kind == "Own Goal For":
            key_events.append({**base, "kind": "own_goal", "player_id": None})
        elif kind in ("Foul Committed", "Bad Behaviour") and base["player_id"]:
            card, label = _card_type(event)
            if card:
                key_events.append({**base, "kind": card, "card_label": label})
        elif kind == "Substitution":
            replacement = event.get("substitution", {}).get("replacement", {})
            key_events.append({
                **base,
                "kind": "substitution",
                "player_in_id": replacement.get("id"),
                "player_in_name": replacement.get("name"),
            })
    return key_events


def summarize_match(match, lineups, raw_events):
    """Réduit un match à ce qui sert au calcul des faits."""
    players = {}
    appearances = []
    for team in lineups:
        for player in team.get("lineup", []):
            players[str(player["player_id"])] = {
                "id": player["player_id"],
                "name": player.get("player_nickname") or player["player_name"],
                "team_id": team["team_id"],
                "country": (player.get("country") or {}).get("name"),
                "number": player.get("jersey_number"),
            }
            if player.get("positions"):
                appearances.append(player["player_id"])

    stadium = match.get("stadium")
    key_events = extract_key_events(raw_events)
    home_id = match["home_team"]["home_team_id"]
    away_id = match["away_team"]["away_team_id"]
    return {
        "id": match["match_id"],
        "competition_id": match["competition"]["competition_id"],
        "competition_name": match["competition"]["competition_name"],
        "season_id": match["season"]["season_id"],
        "season_name": match["season"]["season_name"],
        "date": match["match_date"],
        "stage": (match.get("competition_stage") or {}).get("name"),
        "home": {"id": home_id, "name": match["home_team"]["home_team_name"]},
        "away": {"id": away_id, "name": match["away_team"]["away_team_name"]},
        "home_score": match["home_score"],
        "away_score": match["away_score"],
        "stadium": {
            "id": stadium["id"],
            "name": stadium["name"],
            "country": (stadium.get("country") or {}).get("name"),
        } if stadium else None,
        "players": players,
        "appearances": appearances,
        "key_events": key_events,
    }


def score_warnings(summary):
    """Compare les buts relevés au score officiel du fichier de matchs."""
    tally = {summary["home"]["id"]: 0, summary["away"]["id"]: 0}
    for event in summary["key_events"]:
        if event["kind"] in ("goal", "own_goal"):
            tally[event["team_id"]] = tally.get(event["team_id"], 0) + 1
    home, away = tally[summary["home"]["id"]], tally[summary["away"]["id"]]
    if (home, away) != (summary["home_score"], summary["away_score"]):
        return [f"Match {summary['id']} : {home}-{away} relevé, {summary['home_score']}-{summary['away_score']} annoncé"]
    return []


def load_summaries(season_keys, cache_dir, target_match_id=None, fetch=download, workers=8):
    """Récupère les résumés de toutes les saisons demandées.

    Seuls les résumés sont conservés en cache : les fichiers d'événements bruts sont
    volumineux et deviennent inutiles une fois réduits.
    """
    cache_dir = Path(cache_dir)
    matches = []
    for competition_id, season_id in season_keys:
        matches.extend(fetch_json(f"data/matches/{competition_id}/{season_id}.json", cache_dir, fetch))

    def load_one(match):
        summary_path = cache_dir / "summaries" / f"{match['match_id']}.json"
        if summary_path.exists():
            return json.loads(summary_path.read_text(encoding="utf-8"))
        raw_events = json.loads(fetch(f"{BASE_URL}/data/events/{match['match_id']}.json"))
        lineups = json.loads(fetch(f"{BASE_URL}/data/lineups/{match['match_id']}.json"))
        summary = summarize_match(match, lineups, raw_events)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, ensure_ascii=False), encoding="utf-8")
        return summary

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(load_one, matches))

"""Moteur de règles déterministes pour les suggestions de commentaires."""


def select_suggestions(event, database, limit=3):
    """Classe les faits compatibles avec l'événement, sans en créer de nouveaux."""
    event_type = event.get("type", "calm")
    trigger = {"temps_mort": "timeout"}.get(event_type, event_type)
    context = {
        "player_id": event.get("player_id"),
        "player_ids": event.get("player_ids", []),
        "team_id": event.get("team_id"),
        "stadium_id": event.get("stadium_id"),
        "match_id": event.get("match_id"),
    }
    candidates = []

    for record in database.get("records", []):
        triggers = record.get("triggers", [])
        if trigger not in triggers and "any" not in triggers:
            continue

        targets = record.get("targets", {})
        if any(
            value not in context["player_ids"]
            if key == "player_id" and context["player_ids"]
            else context.get(key) != value
            for key, value in targets.items()
        ):
            continue

        score = record.get("priority", 0)
        score += 60 if trigger in triggers else 0
        score += 40 if record.get("targets", {}).get("player_id") else 0
        score += 25 if record.get("targets", {}).get("team_id") else 0
        score += 20 if record.get("targets", {}).get("stadium_id") else 0
        score += 10 if record.get("targets", {}).get("match_id") else 0
        candidates.append((score, record))

    candidates.sort(key=lambda item: (-item[0], item[1]["id"]))
    return [
        {
            "title": record["title"],
            "fact": record["fact"],
            "source_id": record["id"],
            "source_label": record.get("source_label", record["id"]),
            "relevance": score,
        }
        for score, record in candidates[: max(0, limit)]
    ]
import json
from pathlib import Path

from app.selector import select_suggestions


DATA_PATH = Path(__file__).parents[1] / "app" / "data" / "demo_data.json"


def load_database():
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def test_goal_surfaces_historical_stadium_performance_first():
    database = load_database()
    event = {
        "type": "goal",
        "player_id": "ines-vela",
        "team_id": "fc-aster",
        "stadium_id": "parc-des-brumes",
    }

    suggestions = select_suggestions(event, database)

    assert suggestions[0]["source_id"] == "hist-vela-brumes-01"
    assert "triplé" in suggestions[0]["fact"]
    assert len(suggestions) <= 3


def test_no_matching_record_means_no_suggestion():
    suggestions = select_suggestions(
        {"type": "goal", "player_id": "inconnu", "stadium_id": "inconnu"},
        load_database(),
    )

    assert suggestions == []


def test_calm_moment_returns_general_match_facts():
    suggestions = select_suggestions(
        {
            "type": "calm",
            "match_id": "match-demo-01",
            "stadium_id": "parc-des-brumes",
        },
        load_database(),
    )

    assert suggestions
    assert all(item["source_id"] for item in suggestions)
    assert any("18 400" in item["fact"] for item in suggestions)


def test_suggestions_are_capped_at_three():
    suggestions = select_suggestions(
        {
            "type": "calm",
            "match_id": "match-demo-01",
            "stadium_id": "parc-des-brumes",
            "team_id": "fc-aster",
        },
        load_database(),
        limit=3,
    )

    assert len(suggestions) == 3


def test_substitution_can_match_both_players():
    suggestions = select_suggestions(
        {
            "type": "substitution",
            "player_ids": ["noe-sorin", "sacha-elve"],
            "team_id": "fc-aster",
        },
        load_database(),
    )

    sources = {item["source_id"] for item in suggestions}
    assert "profile-sorin-01" in sources
    assert "profile-elve-01" in sources